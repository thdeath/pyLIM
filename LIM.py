"""
This is the first attempt at creating a linear inverse model in Python
using Greg Hakim's matlab script as a template.  I hope to eventually
turn this into a general linear inverse modelling tool

Currently performing a LIM study on surface temps to try and recreate
the findings from Newman 2014.  Script assumes that it is already in
monthly mean format.

"""

import numpy as np
from scipy.io import netcdf as ncf
from scipy.signal import convolve
from scipy.sparse.linalg import eigs
import Stats as st
import matplotlib.pyplot as plt
from time import time
from random import sample
import os

#Clear all previous plots
plt.close('all')

wsize = 12
var_name = 'air'
neigs = 20
num_trials = 150 
forecast_tlim = 144 #months
NCO = True #NetCDF Operators Flag, always false on Windows for now

if os.name == 'nt':
    data_file = "G:/Hakim Research/data/20CR/air.2m.mon.mean.nc"
    NCO = False
else:
    #data_file = '/home/melt/wperkins/data/ccsm4_last_mil/tas_Amon_CCSM4_past1000_r1i1p1_085001-185012.nc'
    data_file = '/home/melt/wperkins/data/20CR/air.2m.mon.mean.nc'
    
#Load netcdf file
f = ncf.netcdf_file(data_file, 'r')
tvar = f.variables[var_name]
#account for data storage as int * scale + offset
try:
    sf = tvar.scale_factor
    offset = tvar.add_offset
    tdata = tvar.data*sf + offset
except AttributeError:
    tdata = tvar.data

#Calc running mean using window size over the data
print "\nCalculating running mean..."
t1 = time()
run_mean, bedge, tedge = st.runMean(f, var_name, wsize, num_procs=2, useNCO=NCO)
t2 = time()
dur = t2 - t1
print "Done! (Completed in %f s)" % dur

#Calculate monthly climatology
new_shp = [run_mean.shape[0]/wsize, wsize] + list(run_mean.shape[1:])
shp_run_mean = run_mean.reshape( new_shp )
print "\nCalculating monthly climatology from running mean..."
mon_climo = np.sum(shp_run_mean, axis=0)/float(new_shp[0])
print "Done!"

#Remove the monthly climo from the running mean
anomaly_srs = (shp_run_mean - mon_climo).reshape(([new_shp[0]*wsize] + new_shp[2:]))

#Calculate EOFs
shp = anomaly_srs.shape
shp_anomaly = anomaly_srs.reshape(shp[0], shp[1]*shp[2])
print "\nCalculating EOFs..."
t1 = time()
eofs, eig_vals, var_pct = st.calcEOF(shp_anomaly.T, neigs)
dur = time() - t1
print "Done! (Completed in %.1f s)" % dur
eof_proj = np.dot(eofs.T, shp_anomaly.T)

print "\nLeading %i EOFS explain %f percent of the total variance" % (neigs, var_pct)

#Start running trials for LIM forecasts
loc = 100 # just for testing right now
time_dim = eof_proj.shape[1] - forecast_tlim
tsample = int(time_dim*0.9)
forecasts = np.zeros( [num_trials, forecast_tlim+1, neigs, (time_dim - tsample)] )
fcast_idxs = np.zeros ((num_trials, (time_dim - tsample)),
                        dtype=np.int16)

for i in range(num_trials):
    print 'Running trial %i' % (i+1)
    #randomize sample of indices for training and testing
    rnd_idx = sample(xrange(time_dim), time_dim)
    train_idx = np.array(rnd_idx[0:tsample])
    indep_idx = np.array(rnd_idx[tsample:])
    fcast_idxs[i] = indep_idx

    for tau in range(forecast_tlim+1):
        x0 = eof_proj[:,train_idx]
        xt = eof_proj[:,(train_idx + tau)]
        xtx0 = np.dot(xt,x0.T) 
        x0x0 = np.dot(x0, x0.T)
        M = np.dot(xtx0, np.linalg.pinv(x0x0))

        #Test on independent data
        x0i = eof_proj[:,indep_idx]
        xti = eof_proj[:,(indep_idx + tau)]
        xfi = np.dot(M, x0i)
        forecasts[i, tau] = xfi
   
#Move into physical space for error calc
#forecast = np.dot(eofs, xfi)[loc]
#true_space = shp_anomaly.T[loc, indep_idx + tau]
#erri = forecast - true_space
#error_stats[i, tau, :] = erri

#Verification Stuff
lead_times = np.array([0, 1, 3, 6, 9, 12])*12
anom_truth = lambda x:  np.array([shp_anomaly.T[loc, (fcast_idxs[i] + x)] for i in len(fcast_idxs)])
true_var = np.array([anom_truth(tau).var() for tau in lead_times]) 
true_mean = np.array([anom_truth(tau).mean() for tau in lead_times])

fcast_var = np.zeros( (len(lead_times), num_trials) )
fcast_mean = np.zeros( fcast_var.shape )

for i in range(len(lead_times)):
     loc_fcast = np.array([np.dot(eofs[loc], fcast[lead_times[i]]) for fcast in forecasts])
     varis = np.zeros( len(loc_fcast) )
     means = np.zeros( varis.shape )
     for j in range(len(loc_fcast)):
         varis[j] = loc_fcast[0:j+1].var() 
         means[j] = loc_fcast[0:j+1].mean()
     fcast_var[i,:] = varis
     fcast_mean[i,:] = means

fig, ax = plt.subplots(2,1, sharex=True)
x = range(fcast_var.shape[1])

for i,var in enumerate(fcast_var):
    ax[0].plot(x, var, linewidth=2, label='Lead Time = %i yr' % (lead_times[i]/12))
    ax[0].legend()
    ax[1].plot(x, fcast_mean[i], linewidth=2)

for line, var in zip(ax[0].get_lines(), true_var):
    ax[0].axhline(y=var, linestyle = '--', color = line.get_color())

ax[0].set_title('Forecast Variance & Mean vs. # Trials (Single Gridpoint)')
ax[1].set_xlabel('Trial #')
ax[0].set_ylabel('Variance (K)')
ax[1].set_ylabel('Mean (K)')

fig.show()
f.close()
