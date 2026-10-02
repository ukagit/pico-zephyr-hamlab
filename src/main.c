/* DL2DBG HamLab: AD9850, PE4302, ADS1115/AD8307, Zephyr shell + HTTP.
 * ADS1115 software I2C on GP16 (SDA) / GP17 (SCL), shared with future OLED.
 */
#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/shell/shell.h>
#include <zephyr/net/socket.h>
#include <zephyr/logging/log.h>
#include <errno.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <stdint.h>
#include <stdbool.h>
#include <unistd.h>
#include "network/network.h"
#include "hamlab_version.h"
#include "hamlab_swr.h"
#include "hamlab_level.h"
#include "oled_font.h"
#include "hamlab_web.h"
LOG_MODULE_REGISTER(hamlab, LOG_LEVEL_INF);
#define PORT 8080
#define MAX_FREQ 40000000U
#define REF_HZ 125000000U
#define I2C_ADDR 0x48
#define I2C_SDA_PIN 16
#define I2C_SCL_PIN 17
#define OLED_ADDR 0x3c
#define ENC_CLK_PIN 15
#define ENC_DT_PIN 14
#define ENC_BUTTON_PIN 13
/* Mean A0-A1 difference, direct FY6900 sweeps at 0.18 V, 1..60 MHz. */
#define A1_ALIGNMENT_DB 0.2244167
#define SWEEP_MAX_POINTS 256
static const struct device *gpio = DEVICE_DT_GET(DT_NODELABEL(gpio0));
#define OUT(p) gpio_pin_configure(gpio,p,GPIO_OUTPUT_INACTIVE)
#define SET(p,v) gpio_pin_set(gpio,p,v)
#define DELAY() k_busy_wait(5)
static K_MUTEX_DEFINE(lock);
static uint32_t frequency_hz;
static uint32_t swr_reference_hz=7100000;
static uint32_t swr_frequency_hz; /* Correction reference frequency; 0 disables SWR. */
static uint32_t power_frequency_hz, meter_cal_hz;
static double power_coupling_db;
static bool power_enabled;
static uint8_t power_forward_channel=1;
static uint8_t attenuation_db;
static int measurement_error = -ENODEV;
static struct { double voltage, dbm, mw, vpp; } meter[2];
static uint8_t ui_mode; /* 0=ATT, 1..7=FREQ step 1..1000000 Hz */
static const uint32_t frequency_steps[] = {1,10,100,1000,10000,100000,1000000};
static uint8_t oled_frame[1024];
static bool oled_available;
struct sweep_point { uint32_t hz; float a0_dbm, a1_dbm; };
struct sweep_setup { uint32_t start, stop, step; uint16_t dwell_ms; uint8_t samples, att, mode; };
static struct sweep_setup sweep_setup;
static struct sweep_setup sweep_recorded[2];
static struct sweep_point sweep_points[2][SWEEP_MAX_POINTS];
static uint16_t sweep_count[2];
static bool sweep_ready[2],sweep_active,sweep_cancel;
static int sweep_error;
static uint16_t sweep_target;
static char sweep_json_buf[32768];
K_SEM_DEFINE(sweep_start_sem,0,1);
static void pulse(int p) { SET(p,1); k_busy_wait(2); SET(p,0); k_busy_wait(2); }
static void dds_byte(uint8_t value) {
    for (int bit=0;bit<8;bit++) { SET(20,(value>>bit)&1); pulse(18); }
}
static void dds_set(uint32_t hz) {
    uint32_t word=(uint32_t)(((uint64_t)hz*UINT64_C(4294967296)+REF_HZ/2)/REF_HZ);
    for(int b=0;b<4;b++) dds_byte((word>>(8*b))&255);
    dds_byte(0); pulse(19);
}
static void atten_set(uint8_t db) {
    /* Original driver clocks six bits, most significant first: db * 2. */
    uint8_t word=db<<1;
    SET(12,0); SET(11,0);
    for(int i=5;i>=0;i--) { SET(10,(word>>i)&1); k_busy_wait(5); pulse(11); }
    SET(10,0); pulse(12);
}
/* Open-drain emulation: never actively drive I2C lines high. */
static void release_line(int p) { gpio_pin_configure(gpio,p,GPIO_INPUT|GPIO_PULL_UP); DELAY(); }
static void low_line(int p) { gpio_pin_configure(gpio,p,GPIO_OUTPUT_LOW); DELAY(); }
static int read_line(int p) { return gpio_pin_get(gpio,p); }
static void i2c_start(void) { release_line(I2C_SDA_PIN); release_line(I2C_SCL_PIN); low_line(I2C_SDA_PIN); low_line(I2C_SCL_PIN); }
static void i2c_stop(void) { low_line(I2C_SDA_PIN); release_line(I2C_SCL_PIN); release_line(I2C_SDA_PIN); }
static int i2c_bit(int bit) {
    if(bit) release_line(I2C_SDA_PIN); else low_line(I2C_SDA_PIN);
    release_line(I2C_SCL_PIN);
    for(int i=0;i<100 && !read_line(I2C_SCL_PIN);i++) DELAY();
    if(!read_line(I2C_SCL_PIN)) { low_line(I2C_SCL_PIN); return -ETIMEDOUT; }
    int result=read_line(I2C_SDA_PIN); low_line(I2C_SCL_PIN); return result;
}
static int i2c_write(uint8_t v) {
    for(int i=7;i>=0;i--) if(i2c_bit((v>>i)&1)<0) return -ETIMEDOUT;
    return i2c_bit(1)==0 ? 0 : -ENXIO;
}
static int oled_write(uint8_t control,const uint8_t *data,size_t count) {
    i2c_start();
    int rc=i2c_write(OLED_ADDR<<1);
    if(!rc)rc=i2c_write(control);
    for(size_t i=0;!rc && i<count;i++)rc=i2c_write(data[i]);
    i2c_stop();
    return rc;
}
static int oled_command(uint8_t cmd) {return oled_write(0,&cmd,1);}
static int oled_init(void) {
    static const uint8_t commands[]={0xae,0xd5,0x80,0xa8,0x3f,0xd3,0x00,
        0x40,0x8d,0x14,0x20,0x02,0xa1,0xc8,0xda,0x12,0x81,0x7f,
        0xd9,0xf1,0xdb,0x40,0xa4,0xa6,0x2e,0xaf};
    for(size_t i=0;i<ARRAY_SIZE(commands);i++) {
        if(oled_command(commands[i]))return -ENXIO;
    }
    return 0;
}
static void oled_text(int page,int col,const char *s) {
    while(*s && col+6<=128) {
        unsigned char c=(unsigned char)*s++;
        if(c<32||c>126)c='?';
        memcpy(&oled_frame[page*128+col],oled_font[c-32],6);
        col+=6;
    }
}
static int oled_flush(void) {
    for(int page=0;page<8;page++) {
        if(oled_command(0xb0|page)||oled_command(0x00)||oled_command(0x10)||
           oled_write(0x40,&oled_frame[page*128],128))return -EIO;
    }
    return 0;
}
static void oled_render_locked(void) {
    char line[32];
    memset(oled_frame,0,sizeof(oled_frame));
    snprintf(line,sizeof(line),"F %u.%06u",frequency_hz/1000000,
             frequency_hz%1000000);
    oled_text(0,0,line);
    if(ui_mode) {
        /* Invert the full yellow band, including the glyph pixels. */
        for(int i=0;i<128;i++)oled_frame[i]=~oled_frame[i];
    }
    if(ui_mode) {
        snprintf(line,sizeof(line),"STEP %u Hz",frequency_steps[ui_mode-1]);
        oled_text(1,0,line);
    } else oled_text(1,0,"DDS / HF-METER");
    if(measurement_error==0) {
        snprintf(line,sizeof(line),"A0 %+.2f dBm",meter[0].dbm);
        oled_text(3,0,line);
        snprintf(line,sizeof(line),"A1 %+.2f dBm",meter[1].dbm);
        oled_text(4,0,line);
    } else {
        oled_text(3,0,"A0 -- dBm");
        oled_text(4,0,"A1 -- dBm");
    }
    snprintf(line,sizeof(line),"ATT %u dB",attenuation_db);
    oled_text(6,0,line);
    if(ui_mode==0)for(int i=6*128;i<7*128;i++)oled_frame[i]=~oled_frame[i];
    oled_text(7,0,"KNOPF: ATT / F STEP");
    if(oled_flush())oled_available=false;
}
static int i2c_read(bool ack) {
    uint8_t v=0;
    for(int i=0;i<8;i++) { int b=i2c_bit(1); if(b<0)return b; v=(v<<1)|b; }
    if(i2c_bit(!ack)<0)return -ETIMEDOUT;
    return v;
}
static int ads_write_config(uint16_t config) {
    i2c_start(); int rc=i2c_write(I2C_ADDR<<1);
    if(!rc)rc=i2c_write(1);
    if(!rc)rc=i2c_write(config>>8);
    if(!rc)rc=i2c_write(config&255);
    i2c_stop(); return rc;
}
static int ads_read_reg(uint8_t reg, uint16_t *out) {
    i2c_start(); int rc=i2c_write(I2C_ADDR<<1);
    if(!rc)rc=i2c_write(reg);
    if(rc) { i2c_stop();return rc; }
    i2c_start(); rc=i2c_write((I2C_ADDR<<1)|1);
    int hi=-1,lo=-1;
    if(!rc)hi=i2c_read(true);
    if(hi>=0)lo=i2c_read(false);
    i2c_stop();
    if(rc)return rc;
    if(hi<0||lo<0)return -EIO;
    *out=(hi<<8)|lo;return 0;
}
static int ads_measure(int channel,double *volts, bool fast) {
    /* Single shot: normal 128 SPS, sweep 860 SPS; same PGA and calibration. */
    uint16_t cfg=0x8000 | ((4+channel)<<12) | 0x0200 | 0x0100 | (fast ? 0x00e0 : 0x0080) | 3;
    int rc=ads_write_config(cfg); if(rc)return rc;
    for(int n=0;n<30;n++) {
        k_msleep(fast ? 1 : 2);
        uint16_t status;
        rc=ads_read_reg(1,&status);if(rc)return rc;
        if(status&0x8000) {
            uint16_t raw;
            rc=ads_read_reg(0,&raw);if(rc)return rc;
            *volts=(int16_t)raw*4.096/32768.0;
            return 0;
        }
    }
    return -ETIMEDOUT;
}
static int measure_locked(bool fast) {
    meter_cal_hz=sweep_active?frequency_hz:power_frequency_hz?power_frequency_hz:swr_frequency_hz?swr_frequency_hz:frequency_hz;
    int rc=0;
    for(int c=0;c<2;c++) {
        double voltage;
        rc=ads_measure(c,&voltage,fast);if(rc)break;
        /* Scope average 50 ohm, 1/7/30 MHz, 2026-10-01; separate A0 and A1 sweeps. */
        double dbm=c==0 ? 39.1979021169*voltage-63.4736278330
                        : 39.7556150827*voltage-63.1440988355+A1_ALIGNMENT_DB;
        dbm+=level_offset(c,meter_cal_hz);
        meter[c].voltage=voltage;meter[c].dbm=dbm;
        meter[c].mw=pow(10.0,dbm/10.0);
        meter[c].vpp=0.6324555320336759*pow(10.0,dbm/20.0);
    }
    measurement_error=rc;
    return rc;
}
static int update_meter(void) {
    k_mutex_lock(&lock,K_FOREVER);
    int rc=sweep_active ? -EBUSY : measure_locked(false);
    k_mutex_unlock(&lock);
    return rc;
}
static int set_freq(uint32_t hz) {
    if(hz>MAX_FREQ)return -ERANGE;
    k_mutex_lock(&lock,K_FOREVER);
    if(sweep_active){k_mutex_unlock(&lock);return -EBUSY;}
    dds_set(hz);frequency_hz=hz;k_mutex_unlock(&lock);return 0;
}
static int set_att(unsigned db) {
    if(db>30)return -ERANGE;
    k_mutex_lock(&lock,K_FOREVER);
    if(sweep_active){k_mutex_unlock(&lock);return -EBUSY;}
    atten_set(db);attenuation_db=db;k_mutex_unlock(&lock);return 0;
}
static void encoder_turn(int direction) {
    k_mutex_lock(&lock,K_FOREVER);
    if(sweep_active){k_mutex_unlock(&lock);return;}
    if(ui_mode==0) {
        int next=(int)attenuation_db+direction;
        if(next>=0 && next<=30){atten_set(next);attenuation_db=next;}
    } else {
        int64_t next=(int64_t)frequency_hz+direction*frequency_steps[ui_mode-1];
        if(next>=0 && next<=MAX_FREQ){dds_set((uint32_t)next);frequency_hz=next;}
    }
    k_mutex_unlock(&lock);
}
static void encoder_thread(void *a,void *b,void *c) {
    ARG_UNUSED(a);ARG_UNUSED(b);ARG_UNUSED(c);
    static const int8_t moves[16]={0,-1,1,0,1,0,0,-1,-1,0,0,1,0,1,-1,0};
    int prev=(gpio_pin_get(gpio,ENC_CLK_PIN)<<1)|gpio_pin_get(gpio,ENC_DT_PIN);
    int accumulated=0,button_last=gpio_pin_get(gpio,ENC_BUTTON_PIN);
    int button_stable=button_last;
    int64_t changed=k_uptime_get();
    while(1) {
        int clk=gpio_pin_get(gpio,ENC_CLK_PIN),dt=gpio_pin_get(gpio,ENC_DT_PIN);
        if(clk>=0&&dt>=0) {
            int now=(clk<<1)|dt;
            if(now!=prev) {
                accumulated+=moves[(prev<<2)|now];prev=now;
                /* Two valid edges also cover encoders with half-step detents. */
                if(accumulated>=2){encoder_turn(1);accumulated=0;}
                if(accumulated<=-2){encoder_turn(-1);accumulated=0;}
            }
        }
        int button=gpio_pin_get(gpio,ENC_BUTTON_PIN);
        if(button>=0) {
            if(button!=button_last){button_last=button;changed=k_uptime_get();}
            if(button!=button_stable && k_uptime_get()-changed>=30) {
                button_stable=button;
                if(button==0) {
                    k_mutex_lock(&lock,K_FOREVER);
                    ui_mode=(ui_mode+1)%8;
                    k_mutex_unlock(&lock);
                }
            }
        }
        k_msleep(2);
    }
}
static void display_thread(void *a,void *b,void *c) {
    ARG_UNUSED(a);ARG_UNUSED(b);ARG_UNUSED(c);
    while(1) {
        k_mutex_lock(&lock,K_FOREVER);
        bool running=sweep_active;
        k_mutex_unlock(&lock);
        if(!running)update_meter();
        if(oled_available && !running) {
            k_mutex_lock(&lock,K_FOREVER);
            oled_render_locked();
            k_mutex_unlock(&lock);
        }
        k_msleep(running?100:400);
    }
}
static void sweep_thread(void *a,void *b,void *c) {
    ARG_UNUSED(a);ARG_UNUSED(b);ARG_UNUSED(c);
    while(1) {
        k_sem_take(&sweep_start_sem,K_FOREVER);
        k_mutex_lock(&lock,K_FOREVER);
        struct sweep_setup run=sweep_setup;
        uint32_t old_frequency=frequency_hz;
        k_mutex_unlock(&lock);
        int error=0;
        for(uint16_t i=0;i<sweep_target;i++) {
            uint32_t hz=run.start+(uint32_t)i*run.step;
            k_mutex_lock(&lock,K_FOREVER);
            if(sweep_cancel){k_mutex_unlock(&lock);error=-ECANCELED;break;}
            dds_set(hz);frequency_hz=hz;
            k_mutex_unlock(&lock);
            if(run.dwell_ms)k_msleep(run.dwell_ms);
            double a0=0,a1=0;
            for(uint8_t sample=0;sample<run.samples;sample++) {
                k_mutex_lock(&lock,K_FOREVER);
                if(sweep_cancel){error=-ECANCELED;k_mutex_unlock(&lock);break;}
                error=measure_locked(true);
                if(!error){a0+=meter[0].dbm;a1+=meter[1].dbm;}
                k_mutex_unlock(&lock);
                if(error)break;
            }
            if(error)break;
            a0/=run.samples;a1/=run.samples;
            if(a0>10.0||a1>10.0){error=-ERANGE;break;}
            k_mutex_lock(&lock,K_FOREVER);
            sweep_points[run.mode][i]=(struct sweep_point){hz,(float)a0,(float)a1};
            sweep_count[run.mode]=i+1;
            k_mutex_unlock(&lock);
        }
        k_mutex_lock(&lock,K_FOREVER);
        dds_set(old_frequency);frequency_hz=old_frequency;
        sweep_error=error;
        sweep_ready[run.mode]=(error==0 && sweep_count[run.mode]==sweep_target);
        sweep_active=false;
        k_mutex_unlock(&lock);
    }
}
/* K_THREAD_DEFINE takes an integer millisecond delay, not k_timeout_t. */
K_THREAD_DEFINE(encoder_id,1536,encoder_thread,NULL,NULL,NULL,6,0,SYS_FOREVER_MS);
K_THREAD_DEFINE(display_id,2048,display_thread,NULL,NULL,NULL,9,0,SYS_FOREVER_MS);
K_THREAD_DEFINE(sweep_id,3072,sweep_thread,NULL,NULL,NULL,8,0,SYS_FOREVER_MS);
/* Called with meter lock held. Numerical SWR withheld near load reference floor. */
static void live_swr_json(char *buf,size_t len) {
    double offset=0,limit=0,rl=0;
    const char *quality="disabled";
    bool numeric=false;
    if(swr_frequency_hz) {
        quality="frequency_out_of_range";
        if(!swr_cal_at(swr_frequency_hz,&offset,&limit)) {
            offset+=level_offset(0,meter_cal_hz)-level_offset(1,meter_cal_hz);
            rl=offset-(meter[0].dbm-meter[1].dbm);
            quality=measurement_error?"measurement_error":sweep_active?"sweep_active":
                meter[1].dbm < -45+level_offset(1,meter_cal_hz)?"low_forward_level":
                meter[0].dbm < -53+level_offset(0,meter_cal_hz)?"reverse_near_noise_floor":
                rl<=0?"invalid_ratio":rl>=limit-3?"near_reference_limit":"ok";
            numeric=!strcmp(quality,"ok");
        }
    }
    char value[32]="null",loss[32]="null";
    if(swr_frequency_hz && !swr_cal_at(swr_frequency_hz,&offset,&limit) && !measurement_error && !sweep_active)
        snprintf(loss,sizeof(loss),"%.2f",rl);
    if(numeric) {
        double gamma=pow(10.0,-rl/20.0);
        snprintf(value,sizeof(value),"%.2f",(1+gamma)/(1-gamma));
    }
    snprintf(buf,len,"{\"enabled\":%s,\"frequency_hz\":%u,\"forward_channel\":1,\"value\":%s,\"return_loss_db\":%s,\"quality\":\"%s\",\"calibration\":\"selfbuilt_umbau1_open\"}",
        swr_frequency_hz?"true":"false",swr_frequency_hz,value,loss,quality);
}
static void power_json(char *buf,size_t len) {
    char forward[40]="null",reverse[40]="null";
    bool valid=power_enabled&&!measurement_error&&!sweep_active;
    /* Separate coupling of each direction must be checked before precision use. */
    if(valid) {
        double factor=pow(10.0,power_coupling_db/10.0)/1000.0;
        int forward_c=power_forward_channel,reverse_c=1-forward_c;
        if(meter[forward_c].dbm>=-65 && meter[forward_c].dbm<=10)snprintf(forward,sizeof(forward),"%.9f",meter[forward_c].mw*factor);
        if(meter[reverse_c].dbm>=-65 && meter[reverse_c].dbm<=10)snprintf(reverse,sizeof(reverse),"%.9f",meter[reverse_c].mw*factor);
    }
    snprintf(buf,len,"{\"enabled\":%s,\"frequency_hz\":%u,\"calibration_frequency_hz\":%u,\"coupling_db\":%.2f,\"forward_channel\":%u,\"forward_w\":%s,\"reverse_w\":%s,\"reference\":\"scope_average_50ohm\"}",
        power_enabled?"true":"false",power_frequency_hz,meter_cal_hz,power_coupling_db,power_forward_channel,forward,reverse);
}
static int state_json(char *buf,size_t len) {
    k_mutex_lock(&lock,K_FOREVER);
    int n=snprintf(buf,len,"{\"name\":\"hamlab\",\"frequency_hz\":%u,\"attenuation_db\":%u,\"measurement_valid\":%s,\"measurement_error\":%d,\"channels\":[{\"calibrated\":true,\"voltage_v\":%.5f,\"dbm\":%.3f,\"mw\":%.6f,\"vpp\":%.6f,\"tap_w\":null},{\"calibrated\":true,\"voltage_v\":%.5f,\"dbm\":%.3f,\"mw\":%.6f,\"vpp\":%.6f,\"tap_w\":null}]}",frequency_hz,attenuation_db,measurement_error==0?"true":"false",measurement_error,meter[0].voltage,meter[0].dbm,meter[0].mw,meter[0].vpp,meter[1].voltage,meter[1].dbm,meter[1].mw,meter[1].vpp);
    if(n>0 && (size_t)n<len) {
        char swr[320],power[400];live_swr_json(swr,sizeof(swr));power_json(power,sizeof(power));
        n=snprintf(buf+n-1,len-(size_t)n+1,",\"swr\":%s,\"power\":%s}",swr,power)+n-1;
    }
    k_mutex_unlock(&lock);return n;
}
static int parse_uint(const char *str,unsigned long *value) {
    if(!str||!*str||*str=='-'||*str=='+')return -EINVAL;
    char *end;errno=0;unsigned long v=strtoul(str,&end,10);
    if(errno||*end)return -EINVAL;
    *value=v;return 0;
}
static bool sweep_json_uint(const char *body,const char *key,uint32_t *out) {
    const char *pos=strstr(body,key);
    if(!pos)return false;
    pos=strchr(pos,':');if(!pos)return false;
    pos++;while(*pos==' '||*pos=='\t')pos++;
    if(*pos<'0'||*pos>'9')return false;
    char *end;errno=0;unsigned long v=strtoul(pos,&end,10);
    if(errno||v>UINT32_MAX||(*end!=','&&*end!='}'&&*end!=' '&&*end!='\r'&&*end!='\n'))return false;
    *out=(uint32_t)v;return true;
}
static int sweep_start(const char *body) {
    uint32_t start,stop,step,dwell,samples;
    if(!sweep_json_uint(body,"\"start_hz\"",&start)||
       !sweep_json_uint(body,"\"stop_hz\"",&stop)||
       !sweep_json_uint(body,"\"step_hz\"",&step)||
       !sweep_json_uint(body,"\"dwell_ms\"",&dwell)||
       !sweep_json_uint(body,"\"samples\"",&samples))return -EINVAL;
    const char *mode=strstr(body,"\"mode\"");
    if(!mode||(mode=strchr(mode,':'))==NULL)return -EINVAL;
    mode++;while(*mode==' '||*mode=='\t')mode++;
    int selected=!strncmp(mode,"\"baseline\"",10)?0:
                 !strncmp(mode,"\"dut\"",5)?1:-1;
    if(selected<0||start<1||stop>MAX_FREQ||stop<start||step<1||
       dwell>1000||samples<1||samples>8||
       (stop-start)/step+1>SWEEP_MAX_POINTS)return -EINVAL;
    uint16_t count=(stop-start)/step+1;
    k_mutex_lock(&lock,K_FOREVER);
    if(sweep_active){k_mutex_unlock(&lock);return -EBUSY;}
    if(selected==1 && (!sweep_ready[0]||sweep_recorded[0].start!=start||
       sweep_recorded[0].stop!=stop||sweep_recorded[0].step!=step||
       sweep_recorded[0].att!=attenuation_db||sweep_count[0]!=count)) {
        k_mutex_unlock(&lock);return -ENOENT;
    }
    sweep_setup=(struct sweep_setup){start,stop,step,(uint16_t)dwell,
                                    (uint8_t)samples,attenuation_db,(uint8_t)selected};
    sweep_recorded[selected]=sweep_setup;
    sweep_count[selected]=0;
    sweep_ready[selected]=false;
    if(selected==0){sweep_ready[1]=false;sweep_count[1]=0;}
    sweep_target=count;sweep_error=0;sweep_cancel=false;sweep_active=true;
    k_mutex_unlock(&lock);
    k_sem_give(&sweep_start_sem);
    return 0;
}
static void sweep_status_json(char *buf,size_t size) {
    k_mutex_lock(&lock,K_FOREVER);
    snprintf(buf,size,"{\"running\":%s,\"mode\":\"%s\",\"points\":%u,\"target\":%u,\"error\":%d,\"baseline_ready\":%s,\"dut_ready\":%s}",
             sweep_active?"true":"false",sweep_setup.mode?"dut":"baseline",
             sweep_count[sweep_setup.mode],sweep_target,sweep_error,
             sweep_ready[0]?"true":"false",sweep_ready[1]?"true":"false");
    k_mutex_unlock(&lock);
}
static int sweep_results_json(void) {
    k_mutex_lock(&lock,K_FOREVER);
    if(!sweep_ready[0] && sweep_count[0]==0){k_mutex_unlock(&lock);return -ENOENT;}
    size_t used=0,cap=sizeof(sweep_json_buf);
#define APPEND(...) do { \
    int n=snprintf(sweep_json_buf+used,cap-used,__VA_ARGS__); \
    if(n<0||(size_t)n>=cap-used){k_mutex_unlock(&lock);return -ENOSPC;} \
    used+=(size_t)n; \
} while(0)
    APPEND("{\"start_hz\":%u,\"step_hz\":%u,\"attenuation_db\":%u,\"baseline\":[",
           sweep_recorded[0].start,sweep_recorded[0].step,sweep_recorded[0].att);
    for(int mode=0;mode<2;mode++) {
        if(mode)APPEND("],\"dut\":[");
        for(uint16_t i=0;i<sweep_count[mode];i++) {
            const struct sweep_point *p=&sweep_points[mode][i];
            APPEND("%s[%u,%.3f,%.3f]",i?",":"",p->hz,(double)p->a0_dbm,(double)p->a1_dbm);
        }
    }
    APPEND("]}");
#undef APPEND
    k_mutex_unlock(&lock);
    return 0;
}
static int cmd_status(const struct shell *sh,size_t argc,char **argv) {
    char json[1600];state_json(json,sizeof(json));shell_print(sh,"%s",json);return 0;
}
static int cmd_info(const struct shell *sh,size_t argc,char **argv) {
    ARG_UNUSED(argc); ARG_UNUSED(argv);
    shell_print(sh,"{\"name\":\"hamlab\",\"version\":\"%s\",\"board\":\"rpi_pico2/rp2350a/m33/w\",\"calibration\":\"Scope average 50 ohm, 1/7/30 MHz, 2026-10-01\",\"a0_calibrated\":true,\"a1_calibrated\":true,\"a1_alignment_db\":%.4f,\"dds_sweep\":true,\"sweep_max_points\":%d}",HAMLAB_VERSION,A1_ALIGNMENT_DB,SWEEP_MAX_POINTS);
    return 0;
}
static int cmd_freq(const struct shell *sh,size_t argc,char **argv) {
    unsigned long v;if(parse_uint(argv[1],&v)||v>MAX_FREQ)return -EINVAL;
    int rc=set_freq(v);if(!rc)shell_print(sh,"DDS: %lu Hz",v);return rc;
}
static int cmd_att(const struct shell *sh,size_t argc,char **argv) {
    unsigned long v;if(parse_uint(argv[1],&v)||v>30)return -EINVAL;
    int rc=set_att(v);if(!rc)shell_print(sh,"ATT: %lu dB",v);return rc;
}
static int cmd_meter(const struct shell *sh,size_t argc,char **argv) {
    int rc=update_meter();if(rc){shell_error(sh,"ADS1115: %d",rc);return rc;}return cmd_status(sh,0,NULL);
}
static int cmd_sweep(const struct shell *sh,size_t argc,char **argv) {
    if(!strcmp(argv[1],"status")) {
        char json[256];sweep_status_json(json,sizeof(json));shell_print(sh,"%s",json);return 0;
    }
    if(!strcmp(argv[1],"stop")) {
        k_mutex_lock(&lock,K_FOREVER);sweep_cancel=true;k_mutex_unlock(&lock);
        shell_print(sh,"Sweep stop requested");return 0;
    }
    if(strcmp(argv[1],"baseline")&&strcmp(argv[1],"dut"))return -EINVAL;
    if(argc!=2 && argc!=5)return -EINVAL;
    unsigned long start=1000000,stop=11000000,step=100000;
    if(argc==5&&(parse_uint(argv[2],&start)||parse_uint(argv[3],&stop)||
                 parse_uint(argv[4],&step)||start>UINT32_MAX||
                 stop>UINT32_MAX||step>UINT32_MAX))return -EINVAL;
    char request[160];
    snprintf(request,sizeof(request),"{\"mode\":\"%s\",\"start_hz\":%lu,\"stop_hz\":%lu,\"step_hz\":%lu,\"dwell_ms\":0,\"samples\":1}",
             argv[1],start,stop,step);
    int rc=sweep_start(request);
    if(rc){shell_error(sh,"Sweep: %d (DUT requires matching baseline)",rc);return rc;}
    shell_print(sh,"Sweep %s: %lu..%lu Hz, step %lu Hz",argv[1],start,stop,step);
    return 0;
}
static int cmd_swr(const struct shell *sh,size_t argc,char **argv) {
    if(argc==2) {
        unsigned long hz=0;
        if(!strcmp(argv[1],"on")) hz=swr_reference_hz;
        else if(strcmp(argv[1],"off") && (parse_uint(argv[1],&hz)||hz<1000000||hz>30000000)) {
            shell_error(sh,"swr on|off|<reference frequency Hz 1000000..30000000>");return -EINVAL;
        }
        k_mutex_lock(&lock,K_FOREVER);swr_frequency_hz=(uint32_t)hz;if(hz)swr_reference_hz=(uint32_t)hz;k_mutex_unlock(&lock);
    }
    int rc=update_meter();if(rc)return rc;
    char json[320];k_mutex_lock(&lock,K_FOREVER);live_swr_json(json,sizeof(json));k_mutex_unlock(&lock);
    shell_print(sh,"%s",json);return 0;
}
static int cmd_power(const struct shell *sh,size_t argc,char **argv) {
    if(argc==2&&!strcmp(argv[1],"off")) {
        k_mutex_lock(&lock,K_FOREVER);power_enabled=false;power_frequency_hz=0;k_mutex_unlock(&lock);
    } else if(argc==3) {
        unsigned long hz;char *end;errno=0;double coupling=strtod(argv[2],&end);
        if(parse_uint(argv[1],&hz)||hz<1000000||hz>30000000||errno||end==argv[2]||*end||!isfinite(coupling)||coupling<0||coupling>80) {
            shell_error(sh,"power <Hz 1000000..30000000> <coupling dB 0..80>|off");return -EINVAL;
        }
        k_mutex_lock(&lock,K_FOREVER);power_frequency_hz=(uint32_t)hz;power_coupling_db=coupling;power_enabled=true;k_mutex_unlock(&lock);
    } else if(argc!=1) {shell_error(sh,"power <Hz> <coupling dB>|off");return -EINVAL;}
    int rc=update_meter();if(rc)return rc;
    char json[400];k_mutex_lock(&lock,K_FOREVER);power_json(json,sizeof(json));k_mutex_unlock(&lock);
    shell_print(sh,"%s",json);return 0;
}
SHELL_STATIC_SUBCMD_SET_CREATE(hamlab_cmds,
    SHELL_CMD_ARG(power,NULL,"power [Hz coupling_dB]|off; A1 forward",cmd_power,1,2),
    SHELL_CMD_ARG(swr,NULL,"swr [on|off|reference Hz]; A1 forward",cmd_swr,1,1),
    SHELL_CMD_ARG(info,NULL,"Firmware version and calibration",cmd_info,1,0),
    SHELL_CMD_ARG(status,NULL,"Current JSON state",cmd_status,1,0),
    SHELL_CMD_ARG(freq,NULL,"freq <Hz> (0..40000000)",cmd_freq,2,0),
    SHELL_CMD_ARG(att,NULL,"att <dB> (0..30)",cmd_att,2,0),
    SHELL_CMD_ARG(meter,NULL,"Read both AD8307 channels",cmd_meter,1,0),
    SHELL_CMD_ARG(sweep,NULL,"sweep baseline|dut [startHz stopHz stepHz], status, stop",cmd_sweep,2,3),
    SHELL_SUBCMD_SET_END);
SHELL_CMD_REGISTER(hamlab,&hamlab_cmds,"HamLab instrument",NULL);
static void send_full(int fd,const char *buf,size_t len) {
    while(len) {
        ssize_t sent=zsock_send(fd,buf,len,0);
        if(sent<=0)return;
        buf+=sent;len-=sent;
    }
}
static void respond(int fd,int code,const char *type,const char *body) {
    char head[256];size_t size=strlen(body);
    int n=snprintf(head,sizeof(head),"HTTP/1.1 %d %s\r\nContent-Type: %s\r\nContent-Length: %zu\r\nConnection: close\r\nCache-Control: no-store\r\n\r\n",code,code==200?"OK":code==400?"Bad Request":code==409?"Conflict":code==503?"Service Unavailable":"Not Found",type,size);
    send_full(fd,head,n);send_full(fd,body,size);
}
static void handle_http(int fd) {
    char req[1024]={0},json[1600];
    ssize_t n=zsock_recv(fd,req,sizeof(req)-1,0);if(n<=0)return;
    req[n]=0;
    while(!strstr(req,"\r\n\r\n") && (size_t)n<sizeof(req)-1) {
        ssize_t got=zsock_recv(fd,req+n,sizeof(req)-1-n,0);
        if(got<=0)return;
        n+=got;req[n]=0;
    }
    char *body=strstr(req,"\r\n\r\n");
    if(!body){respond(fd,400,"text/plain","HTTP-Header unvollständig");return;}
    size_t content_length=0;
    for(char *line=req;line<body;) {
        char *next=strstr(line,"\r\n");if(!next||next>body)break;
        if(!strncasecmp(line,"Content-Length:",15))content_length=strtoul(line+15,NULL,10);
        line=next+2;
    }
    if(content_length>sizeof(req)-1-(size_t)(body+4-req)) {
        respond(fd,400,"text/plain","JSON zu groß");return;
    }
    while((size_t)(req+n-(body+4))<content_length) {
        ssize_t got=zsock_recv(fd,req+n,sizeof(req)-1-n,0);
        if(got<=0)return;
        n+=got;req[n]=0;
    }
    if(!strncmp(req,"GET /compact ",13) || !strncmp(req,"GET /compact.html ",18)) {respond(fd,200,"text/html; charset=utf-8",compact_html);return;}
    if(!strncmp(req,"GET / ",6)) {respond(fd,200,"text/html; charset=utf-8",html);return;}
    if(!strncmp(req,"GET /sweep.js ",sizeof("GET /sweep.js ")-1)) {
        respond(fd,200,"text/javascript; charset=utf-8",sweep_js);return;
    }
    if(!strncmp(req,"GET /api/v1/sweep/status ",sizeof("GET /api/v1/sweep/status ")-1)) {
        sweep_status_json(json,sizeof(json));respond(fd,200,"application/json",json);return;
    }
    if(!strncmp(req,"GET /api/v1/sweep/results ",sizeof("GET /api/v1/sweep/results ")-1)) {
        int rc=sweep_results_json();
        if(rc)respond(fd,rc==-EBUSY?409:404,"text/plain",rc==-EBUSY?"Sweep läuft":"Keine vollständige Baseline");
        else respond(fd,200,"application/json",sweep_json_buf);
        return;
    }
    if(!strncmp(req,"POST /api/v1/sweep/start ",sizeof("POST /api/v1/sweep/start ")-1)) {
        if(!body){respond(fd,400,"text/plain","JSON fehlt");return;}
        int rc=sweep_start(body+4);
        if(rc)respond(fd,rc==-EBUSY?409:400,"text/plain",
                      rc==-EBUSY?"Sweep läuft":rc==-ENOENT?"Passende Baseline fehlt":"Ungültige Sweep-Parameter");
        else {sweep_status_json(json,sizeof(json));respond(fd,200,"application/json",json);}
        return;
    }
    if(!strncmp(req,"POST /api/v1/sweep/stop ",sizeof("POST /api/v1/sweep/stop ")-1)) {
        k_mutex_lock(&lock,K_FOREVER);sweep_cancel=true;k_mutex_unlock(&lock);
        sweep_status_json(json,sizeof(json));respond(fd,200,"application/json",json);return;
    }
    if(!strncmp(req,"GET /api/v1/measure ",20)) {
        int rc=update_meter();state_json(json,sizeof(json));respond(fd,rc==-EBUSY?409:rc?503:200,"application/json",json);return;
    }
    if(!strncmp(req,"GET /api/v1/state ",18)) {state_json(json,sizeof(json));respond(fd,200,"application/json",json);return;}
    if(!strncmp(req,"GET /api/v1/info ",17)) {
        snprintf(json,sizeof(json),"{\"name\":\"hamlab\",\"version\":\"%s\",\"board\":\"rpi_pico2/rp2350a/m33/w\",\"calibration\":\"Scope average 50 ohm, 1/7/30 MHz, 2026-10-01\",\"a0_calibrated\":true,\"a1_calibrated\":true,\"a1_alignment_db\":%.4f,\"dds_sweep\":true,\"sweep_max_points\":%d}",HAMLAB_VERSION,A1_ALIGNMENT_DB,SWEEP_MAX_POINTS);
        respond(fd,200,"application/json",json);return;
    }
    if(!strncmp(req,"POST /api/v1/power ",19)) {
        uint32_t enabled,hz,coupling,channel;
        if(!body ||
           !sweep_json_uint(body+4,"\"enabled\"",&enabled) ||
           !sweep_json_uint(body+4,"\"frequency_hz\"",&hz) ||
           !sweep_json_uint(body+4,"\"coupling_millidb\"",&coupling) ||
           !sweep_json_uint(body+4,"\"forward_channel\"",&channel) ||
           enabled>1 || hz<1000000 || hz>30000000 || coupling>80000 || channel>1) {
            respond(fd,400,"text/plain","Invalid power configuration");return;
        }
        k_mutex_lock(&lock,K_FOREVER);
        if(sweep_active){k_mutex_unlock(&lock);respond(fd,409,"text/plain","Sweep läuft");return;}
        power_enabled=enabled;power_frequency_hz=enabled?hz:0;
        power_coupling_db=coupling/1000.0;power_forward_channel=(uint8_t)channel;
        k_mutex_unlock(&lock);
        int rc=update_meter();
        state_json(json,sizeof(json));respond(fd,rc?503:200,"application/json",json);return;
    }
    if(!strncmp(req,"POST /api/v1/config ",20)) {
        if(!body) {respond(fd,400,"text/plain","Missing body");return;}
        body+=4;
        char *key=NULL;bool freq=false,swr=false;
        if((key=strstr(body,"\"swr_frequency_hz\"")))swr=true;
        else if((key=strstr(body,"\"frequency_hz\"")))freq=true;
        else key=strstr(body,"\"attenuation_db\"");
        if(!key || !(key=strchr(key,':'))) {respond(fd,400,"text/plain","Expected frequency_hz or attenuation_db");return;}
        key++;while(*key==' '||*key=='\t')key++;
        /* Accept one integer field. HTTP server is intended for a trusted LAN. */
        unsigned long value;char number[24];size_t i=0;
        while(key[i]>='0'&&key[i]<='9'&&i<sizeof(number)-1){number[i]=key[i];i++;}
        number[i]=0;
        if(!i || (key[i]!='}'&&key[i]!=','&&key[i]!=' '&&key[i]!='\r'&&key[i]!='\n') || parse_uint(number,&value) || (swr?(value!=0&&(value<1000000||value>30000000)):freq?value>MAX_FREQ:value>30)) {respond(fd,400,"text/plain","Value out of range");return;}
        int rc=0;
        if(swr){k_mutex_lock(&lock,K_FOREVER);swr_frequency_hz=(uint32_t)value;if(value)swr_reference_hz=(uint32_t)value;k_mutex_unlock(&lock);}
        else rc=freq?set_freq(value):set_att(value);
        if(rc){respond(fd,rc==-EBUSY?409:400,"text/plain",rc==-EBUSY?"Sweep läuft":"Invalid value");return;}
        state_json(json,sizeof(json));respond(fd,200,"application/json",json);return;
    }
    respond(fd,404,"text/plain","Not found");
}
static void http_thread(void *arg1, void *arg2, void *arg3) {
    ARG_UNUSED(arg1); ARG_UNUSED(arg2); ARG_UNUSED(arg3);
    int s=zsock_socket(AF_INET,SOCK_STREAM,IPPROTO_TCP);
    if(s<0){LOG_ERR("socket: %d",errno);return;}
    struct sockaddr_in addr={.sin_family=AF_INET,.sin_port=htons(PORT),.sin_addr.s_addr=INADDR_ANY};
    if(zsock_bind(s,(struct sockaddr *)&addr,sizeof(addr))<0||zsock_listen(s,2)<0){LOG_ERR("HTTP bind/listen: %d",errno);zsock_close(s);return;}
    LOG_INF("HTTP on port %d",PORT);
    while(1) {
        int c=zsock_accept(s,NULL,NULL);if(c<0){k_msleep(100);continue;}
        struct timeval tv={.tv_sec=2};zsock_setsockopt(c,SOL_SOCKET,SO_RCVTIMEO,&tv,sizeof(tv));
        handle_http(c);zsock_close(c);
    }
}
K_THREAD_DEFINE(http_id,6144,http_thread,NULL,NULL,NULL,7,0,0);
int main(void) {
    if(!device_is_ready(gpio)){LOG_ERR("GPIO not ready");return 0;}
    const int pins[]={18,19,20,21,10,11,12};
    for(size_t i=0;i<ARRAY_SIZE(pins);i++)OUT(pins[i]);
    release_line(I2C_SDA_PIN);release_line(I2C_SCL_PIN);
    gpio_pin_configure(gpio,ENC_CLK_PIN,GPIO_INPUT|GPIO_PULL_UP);
    gpio_pin_configure(gpio,ENC_DT_PIN,GPIO_INPUT|GPIO_PULL_UP);
    gpio_pin_configure(gpio,ENC_BUTTON_PIN,GPIO_INPUT|GPIO_PULL_UP);
    oled_available=(oled_init()==0);
    pulse(21);pulse(18);pulse(19); /* AD9850 serial mode */
    set_freq(1000000);set_att(0);
    k_thread_start(encoder_id);
    k_thread_start(display_id);
    k_thread_start(sweep_id);
    LOG_INF("OLED %s, encoder GP15/GP14, button GP13",oled_available?"ready":"not found");
    int net_rc=hamlab_network_start();
    LOG_INF("HamLab ready. Wi-Fi autostart: %d; USB shell: hamlab status", net_rc);
    return 0;
}
