#ifndef HAMLAB_SWR_H
#define HAMLAB_SWR_H
#include <stdint.h>
#include <math.h>
/* Self-built DJ0ABR coupler, closed lid, FY6900; A1 forward, A0 reverse.
 * Open normalization only. Load curve is a quality reference, not vector correction. */
static const struct { uint32_t hz; double open_delta, limit; } swr_cal[] = {
    {1000000U, 0.028000, 26.111000},
    {2000000U, 0.032000, 26.028000},
    {3000000U, 0.054000, 26.091000},
    {4000000U, 0.037000, 26.194000},
    {5000000U, 0.015000, 26.325000},
    {6000000U, 0.039000, 26.449000},
    {7000000U, 0.030000, 26.574000},
    {8000000U, 0.054000, 26.769000},
    {9000000U, 0.027000, 26.909000},
    {10000000U, 0.093000, 27.176000},
    {11000000U, 0.033000, 27.389000},
    {12000000U, 0.004000, 27.570000},
    {13000000U, 0.007000, 27.872000},
    {14000000U, 0.008000, 28.095000},
    {15000000U, 0.009000, 28.377000},
    {16000000U, -0.007000, 28.672000},
    {17000000U, -0.002000, 28.966000},
    {18000000U, 0.011000, 29.306000},
    {19000000U, -0.012000, 29.611000},
    {20000000U, 0.065000, 30.167000},
    {21000000U, -0.024000, 30.178000},
    {22000000U, -0.053000, 30.438000},
    {23000000U, -0.041000, 30.592000},
    {24000000U, -0.045000, 30.827000},
    {25000000U, -0.054000, 30.619000},
    {26000000U, -0.054000, 31.042000},
    {27000000U, -0.051000, 31.227000},
    {28000000U, -0.051000, 31.100000},
    {29000000U, -0.052000, 30.817000},
    {30000000U, -0.080000, 30.706000},
};
static inline int swr_cal_at(uint32_t hz, double *offset, double *limit) {
    unsigned count=sizeof(swr_cal)/sizeof(swr_cal[0]);
    if(hz<swr_cal[0].hz || hz>swr_cal[count-1].hz) return -1;
    for(unsigned i=1;i<count;i++) if(hz<=swr_cal[i].hz) {
        double t=(double)(hz-swr_cal[i-1].hz)/(swr_cal[i].hz-swr_cal[i-1].hz);
        *offset=swr_cal[i-1].open_delta+t*(swr_cal[i].open_delta-swr_cal[i-1].open_delta);
        *limit=swr_cal[i-1].limit+t*(swr_cal[i].limit-swr_cal[i-1].limit);
        return 0;
    }
    return -1;
}
#endif
