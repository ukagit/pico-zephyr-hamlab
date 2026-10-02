#include <errno.h>
#include <zephyr/kernel.h>
#include <zephyr/net/net_if.h>
#include <zephyr/net/net_mgmt.h>
#include <zephyr/net/wifi_mgmt.h>
#include <zephyr/shell/shell.h>
#include <zephyr/sys/atomic.h>
#include "network.h"
#define WIFI_CONNECT_TIMEOUT_MS 20000
#define WIFI_RETRY_MS 5000
K_SEM_DEFINE(wifi_start_sem, 0, 1);
static atomic_t wifi_attempts = ATOMIC_INIT(0);
static atomic_t wifi_error = ATOMIC_INIT(0);
static atomic_t wifi_state = ATOMIC_INIT(0); /* 0 idle, 1 connecting, 2 online, 3 retry, 4 no iface */
int hamlab_network_start(void)
{
    if (net_if_get_first_wifi() == NULL) return -ENODEV;
    k_sem_give(&wifi_start_sem);
    return 0;
}
static void wifi_thread(void *p1,void *p2,void *p3)
{
    ARG_UNUSED(p1); ARG_UNUSED(p2); ARG_UNUSED(p3);
    k_sem_take(&wifi_start_sem,K_FOREVER);
    while (true) {
        struct net_if *iface=net_if_get_first_wifi();
        if (!iface) {
            atomic_set(&wifi_state,4); atomic_set(&wifi_error,-ENODEV);
            k_msleep(WIFI_RETRY_MS);continue;
        }
        if (net_if_oper_state(iface)==NET_IF_OPER_UP) {
            atomic_set(&wifi_state,2); atomic_set(&wifi_error,0);
            k_sleep(K_SECONDS(2));continue;
        }
        atomic_set(&wifi_state,1);atomic_inc(&wifi_attempts);
        int rc=net_mgmt(NET_REQUEST_WIFI_CONNECT_STORED,iface,NULL,0);
        if(rc)atomic_set(&wifi_error,rc);
        for(int waited=0;waited<WIFI_CONNECT_TIMEOUT_MS;waited+=500) {
            if(net_if_oper_state(iface)==NET_IF_OPER_UP)break;
            k_msleep(500);
        }
        if(net_if_oper_state(iface)==NET_IF_OPER_UP)continue;
        if(!rc)atomic_set(&wifi_error,-ETIMEDOUT);
        atomic_set(&wifi_state,3);k_msleep(WIFI_RETRY_MS);
    }
}
K_THREAD_DEFINE(hamlab_wifi_id,2048,wifi_thread,NULL,NULL,NULL,11,0,0);
static int cmd_wifi_stored(const struct shell *sh,size_t argc,char **argv)
{
    ARG_UNUSED(argc);ARG_UNUSED(argv);
    int rc=hamlab_network_start();
    if(rc)shell_error(sh,"Wi-Fi start: %d",rc);
    else shell_print(sh,"Stored Wi-Fi connection requested");
    return rc;
}
static int cmd_network_status(const struct shell *sh,size_t argc,char **argv)
{
    ARG_UNUSED(argc);ARG_UNUSED(argv);
    const char *names[]={"idle","connecting","online","retry_wait","no_interface"};
    int state=atomic_get(&wifi_state);
    shell_print(sh,"wifi_state: %s",state>=0&&state<5?names[state]:"unknown");
    shell_print(sh,"wifi_attempts: %ld",(long)atomic_get(&wifi_attempts));
    shell_print(sh,"wifi_error: %ld",(long)atomic_get(&wifi_error));
    shell_print(sh,"TCP console: port 23; HTTP: port 8080");
    return 0;
}
SHELL_CMD_REGISTER(wifi_stored,NULL,"Connect with saved Wi-Fi credentials",cmd_wifi_stored);
SHELL_CMD_REGISTER(network_status,NULL,"Show Wi-Fi connection state",cmd_network_status);
