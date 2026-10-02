#ifndef HAMLAB_LEVEL_H
#define HAMLAB_LEVEL_H
#include <stdint.h>
/* Scope-average reference, 50 ohm sine, 2026-10-01. Offsets include
 * the previous A1 alignment. Endpoints held outside 1..30 MHz. */
static inline double level_offset(int channel,uint32_t hz) {
    const double a[2][3]={{-19.47,-19.39,-18.35},{-19.60,-19.50,-18.46}};
    if(hz<=1000000U)return a[channel][0];
    if(hz>=30000000U)return a[channel][2];
    unsigned i=hz<=7000000U?0:1;
    double lo=i?7000000.0:1000000.0,hi=i?30000000.0:7000000.0;
    return a[channel][i]+(a[channel][i+1]-a[channel][i])*((double)hz-lo)/(hi-lo);
}
#endif
