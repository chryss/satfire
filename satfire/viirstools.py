#!/usr/bin/env python
"""
Helper functions for processing VIIRS HDF5 files in order to
extract fire information. And for plotting on a map.

Chris Waigl, 2016-03-01
Refactored and reduced for separate release, CW, 2019-08-25
"""

import os
import glob
import re
import datetime as dt
from collections import OrderedDict
import numpy as np
import seaborn as sns
from matplotlib import pyplot as plt
from mpl_toolkits.basemap import Basemap
from shapely.geometry import Polygon
from pygaarst import raster
from pygaarst.rasterhelpers import PygaarstRasterError

earth = 'cornsilk'
water = 'lightskyblue'

BANDFILES = {
    u'dnb': ['SVDNB', u'GDNBO'],
    u'iband': [u'SVI01', u'SVI02', u'SVI03', u'SVI04', u'SVI05', u'GITCO'],
    u'mband': [u'SVM01', u'SVM02', u'SVM03', u'SVM04', u'SVM05',
               u'SVM06', u'SVM07', u'SVM08', u'SVM09', u'SVM10',
               u'SVM11', u'SVM12', u'SVM13', u'SVM14', u'SVM15',
               u'SVM16', u'GMTCO'],
}

def getgoodrows(coordarraysarray, minval=-180., maxval=180.):
    """Returns first and last row idx for which all elements are between min and max

    In VIIRS latitude/longitude arrays, -999.23 is used as a fill value """
    goodrows = np.where(np.all(
        (coordarraysarray > minval) & (coordarraysarray < maxval), axis=1))[0]
    return goodrows[0], goodrows[-1]


def dedupedlist(mylist):
    """Dedupe a list"""
    return list(OrderedDict.fromkeys(mylist))


def getdefaultsubdirs(basedir):
    """Get all scene subdirs of a directory according to default naming scheme"""
    return sorted(glob.glob(
        basedir + ('/20[0-1][0-9]_[0-1][0-9]_[0-3][0-9]_'
                   '[0-9][0-9][0-9]_[0-2][0-9][0-6][0-9]')))

def getmatches(datafilelist, regex=None):
    """Takes list of search strings + regex. Returns a list of match objects"""
    if not regex:
        regex = re.compile(
            r"""
            (?P<ftype>[A-Z0-9]{5})      # band type of data file
            _[a-z]+                     # sat id
            _d(?P<date>\d{8})           # acq date
            _t(?P<time>\d{7})           # granule start time UTC
            _e\d+                       # granule end time UTC
            _b(?P<orbit>\d+)            # orbit number
            _c\d+                       # file creation date/time
            _\w+.h5                     # more stuff
            """, re.X
        )
    return [regex.search(filename) for filename in datafilelist]


def getoverpasses(basedir, scenelist=[], ):
    """Get list of dict of overpasses, file names classified by band type"""
    if scenelist:
        subdirs = filter(
            os.path.isdir,
            [os.path.join(basedir, item) for item in scenelist])
    else:
        subdirs = getdefaultsubdirs(basedir)
    overpasses = OrderedDict()
    for subdir in subdirs:
        basename = os.path.split(subdir)[-1]
        overpasses[basename] = {}
        if os.path.isdir(os.path.join(subdir, 'sdr')):
            overpasses[basename]['dir'] = os.path.join(subdir, 'sdr')
        else:
            overpasses[basename]['dir'] = subdir
        datafiles = sorted(
            [item for item in os.listdir(
                overpasses[basename]['dir']) if item.endswith('.h5')])
        if len(datafiles) % 25 != 0:
            overpasses[basename]['message'] = "Some data files are missing in {}: {} is not divisible by 25".format(
                basename, len(datafiles))
        numgran = len(datafiles) // 25
        overpasses[basename]['numgranules'] = numgran
        mos = getmatches(datafiles)
        overpasses[basename]['datetimes'] = dedupedlist(
            [mo.groupdict()['date'] + '_' + mo.groupdict()['time'] for mo in mos])
        for ftype in [mo.groupdict()['ftype'] for mo in mos]:
            overpasses[basename][ftype] = [
                filename for filename in datafiles if filename.startswith(ftype)]
    return overpasses


def getoverpassesbygranulefordir(dirname):
    overpasses = {}
    if os.path.isdir(os.path.join(dirname, 'sdr')):
        overpasses['dir'] = os.path.join(dirname, 'sdr')
    else:
        overpasses['dir'] = dirname
    datafiles = sorted([item for item in os.listdir(
        overpasses['dir']) if item.endswith('.h5')])
    if len(datafiles) % 25 != 0:
        overpasses['message'] = "Some data files are missing in {}: {} is not divisible by 25".format(
            dirname, len(datafiles))
    mos = getmatches(datafiles)
    for mo, fname in zip(mos, datafiles):
        granulestr = mo.groupdict()['date'] + '_' + mo.groupdict()['time']
        ftype = mo.groupdict()['ftype']
        try:
            overpasses[granulestr][ftype] = fname
        except KeyError:
            overpasses[granulestr] = {}
            overpasses[granulestr][ftype] = fname
    return overpasses


def getfilesbygranule(basedir, scenelist=[]):
    if scenelist:
        subdirs = filter(os.path.isdir, [os.path.join(
            basedir, item) for item in scenelist])
    else:
        subdirs = getdefaultsubdirs(basedir)
    overpasses = OrderedDict()
    for subdir in subdirs:
        basename = os.path.split(subdir)[-1]
        overpasses[basename] = getoverpassesbygranulefordir(subdir)
        overpasses[basename]['dir'] = subdir
    return overpasses


def checkdir(basedir, subdirlist=[]):
    if not subdirlist:
        dirlist = sorted(glob.glob(os.path.join(basedir, "201*")))
    else:
        dirlist = filter(os.path.isdir, [os.path.join(
            basedir, item) for item in subdirlist])
    for dir in dirlist:
        dirname = os.path.split(dir)[1]
        errormsg = None
        try:
            numfiles = len(glob.glob(os.path.join(dir, "sdr", "*.h5")))
        except IOError:
            errormsg = "No data files found"
        if errormsg:
            print("{}: {}".format(dirname, errormsg))
        elif numfiles % 25 != 0:
            print("{}: {}".format(dirname, numfiles))


def getedge(viirsdataset, step=50):
    frst, lst = getgoodrows(viirsdataset.lats)
    edgelons = np.concatenate((
        viirsdataset.lons[frst, ::step],
        viirsdataset.lons[frst:lst - step:step, -1],
        viirsdataset.lons[lst, ::-step],
        viirsdataset.lons[lst:frst:-step, 0]))
    edgelats = np.concatenate((
        viirsdataset.lats[frst, ::step],
        viirsdataset.lats[frst:lst - step:step, -1],
        viirsdataset.lats[lst, ::-step],
        viirsdataset.lats[lst:frst:-step, 0]))
    return edgelons, edgelats


def checkviirsganulecomplete(granuledict, dataset='iband'):
    dataset = dataset.lower()
    complete = True
    if dataset not in BANDFILES.keys():
        print("Unknown band type '{}' for viirs granule. Valid values are: {}.".format(
            dataset, ', '.join(BANDFILES.keys())))
        return
    complete = True
    for bandname in BANDFILES[dataset]:
        try:
            if not granuledict[bandname]:
                complete = False
                print("detected missing band {}".format(bandname))
                return complete
        except KeyError:
            complete = False
            print("detected missing key for band {}".format(bandname))
            return complete
    return complete


def getgranulecatalog(basedir, scenelist=None):
    intermediary = getfilesbygranule(basedir, scenelist=scenelist)
    catalog = {}
    for overpass in intermediary:
        for granule in intermediary[overpass]:
            if granule in ['dir', 'message']:
                continue
            print(granule)
            catalog[granule] = intermediary[overpass][granule]
            catalog[granule][u'dir'] = intermediary[overpass]['dir']
            for datasettype in BANDFILES:
                catalog[granule][datasettype + u'_complete'
                                 ] = checkviirsganulecomplete(catalog[granule])
            if catalog[granule][u'iband_complete']:
                try:
                    viirs = raster.VIIRSHDF5(os.path.join(
                        catalog[granule][u'dir'],
                        catalog[granule][u'SVI01']))
                except (PygaarstRasterError, IOError) as err:
                    print("cannot access data file for I-band in {}".format(
                        granule))
                    print(err)
                    catalog[granule][u'iband_complete'] = False
                    continue
                catalog[granule][u'granuleID'] = viirs.meta[
                    u'Data_Product'][u'AggregateBeginningGranuleID']
                catalog[granule][u'orbitnumber'] = viirs.meta[
                    u'Data_Product'][u'AggregateBeginningOrbitNumber']
                try:
                    catalog[granule][u'ascending_node'] = viirs.ascending_node
                    edgelons, edgelats = getedge(viirs)
                except (PygaarstRasterError, IOError) as err:
                    print("cannot access geodata file for I-band in {}".format(
                        granule))
                    print(err)
                    catalog[granule][u'iband_complete'] = False
                    continue
                catalog[granule][u'edgepolygon_I'] = Polygon(
                    zip(edgelons, edgelats)).wkt
                try:
                    viirs.close()
                except (PygaarstRasterError, IOError) as err:
                    print("cannot access some necessary file file for I-band in {}".format(
                        granule))
                    print(err)
                    catalog[granule][u'iband_complete'] = False
                    continue
    return catalog


def generate_overviewbase(
        width=2000000, height=1800000,
        resolution='l', projection='aea',
        lat_1=60., lat_2=70., lat_0=65, lon_0=-150,
        rivercolor=water, continentcolor=earth,
        lakecolor=water, oceancolor=water,
        meridianrange=np.arange(-180, 180, 5),
        meridianlabels=[False, False, False, 1],
        parallelrange=np.arange(0, 80, 2),
        parallellabels=[1, 1, False, False]
):
    mm = Basemap(
        width=width, height=height,
        resolution=resolution,
        projection='aea',
        lat_1=lat_1, lat_2=lat_2, lat_0=lat_0, lon_0=lon_0)
    mm.drawcoastlines()
    mm.drawrivers(color=rivercolor, linewidth=1.5)
    mm.drawmeridians(meridianrange, labels=meridianlabels)
    mm.drawparallels(parallelrange, labels=parallellabels)
    mm.fillcontinents(
        color=continentcolor,
        lake_color=lakecolor)
    mm.drawmapboundary(fill_color=oceancolor)
    return mm


def makeoverviewplot(viirsdatasets=[], datasetname=None, labels=[], earth=earth, water=water):
    fig1 = plt.figure(1, figsize=(15, 15))
    ax1 = fig1.add_subplot(111)
    mm = generate_overviewbase()
    if not labels or len(labels) != len(viirsdatasets):
        labels = map(str, range(len(viirsdatasets)))
    if viirsdatasets:
        current_palette = sns.color_palette(
            "Paired", n_colors=len(viirsdatasets))
        for idx, viirsdataset in enumerate(viirsdatasets):
            lons, lats = getedge(viirsdataset)
            x, y = mm(lons, lats)
            ax1.plot(x, y,
                     linewidth=3, color=current_palette[idx], label=labels[idx])
    plt.legend()
    ax1.set_title('Alaska VIIRS overpass: {}'.format(datasetname))
    plt.show()


def makeplot(viirsdatasetlist, title=None, band='i4'):
    """Makes a plot of a single-band VIIRS HDF5 dataset object, I4 band"""
    fig1 = plt.figure(1, figsize=(20, 20))
    ax1 = fig1.add_subplot(111)
    # mapbase
    mm = generate_overviewbase()    # data
    for viirsdataset in viirsdatasetlist:
        mult, add = viirsdataset.I4['BrightnessTemperatureFactors'][:]
        i4tb = viirsdataset.I4['BrightnessTemperature'][:]
        basemasked_i4tb = np.ma.masked_where(i4tb == np.max(i4tb), i4tb)
        basemasked_i4tb_scaled = basemasked_i4tb * mult + add
        xx, yy = mm(viirsdataset.lons, viirsdataset.lats)
        dataplt = mm.pcolormesh(
            xx, yy, basemasked_i4tb_scaled, edgecolors='None', vmin=280, vmax=370, zorder=10)

    if not title:
        datestamp = getdatestamp_AKDT(viirsdataset)
        ax1.set_title('Western Alaska: Brightness temperature from band {}, {}'.format(
            viirsdataset.meta['Data_Product']['N_Collection_Short_Name'], datestamp))
    else:
        ax1.set_title(title)
    mm.drawcoastlines(color="slategrey", zorder=20)
    cbar = mm.colorbar(dataplt, location='bottom', pad="15%")
    cbar.set_label("$T_B$ in $K$")


def getdatestamp_AKDT(viirsdataset, idx=None, spaces=True):
    if idx is not None:
        timestamp = (viirsdataset.meta['Data_Product'][idx]['AggregateBeginningDate'] +
                     u'_' + viirsdataset.meta['Data_Product'][idx]['AggregateBeginningTime'])
    else:
        timestamp = (viirsdataset.meta['Data_Product']['AggregateBeginningDate'] +
                     u'_' + viirsdataset.meta['Data_Product']['AggregateBeginningTime'])
    if spaces:
        datestamp_AK = (dt.datetime.strptime(timestamp, '%Y%m%d_%H%M%S.%fZ') +
                        dt.timedelta(hours=-8)).strftime('%Y-%m-%d %H:%M:%S AKDT')
    else:
        datestamp_AK = (dt.datetime.strptime(timestamp, '%Y%m%d_%H%M%S.%fZ') +
                        dt.timedelta(hours=-8)).strftime('%Y%m%d_%H%M%S_AKDT')
    return datestamp_AK


def get_date_UTC(viirsdataset, idx=None):
    if idx is not None:
        dateutc = viirsdataset.meta['Data_Product'][idx]['AggregateBeginningDate']
    else:
        dateutc = viirsdataset.meta['Data_Product']['AggregateBeginningDate']
    return dt.datetime.strptime(dateutc, '%Y%m%d').strftime('%Y-%m-%d')


def get_time_UTC(viirsdataset, idx=None):
    if idx is not None:
        timeutc = viirsdataset.meta['Data_Product'][idx]['AggregateBeginningTime']
    else:
        timeutc = viirsdataset.meta['Data_Product']['AggregateBeginningTime']
    return dt.datetime.strptime(timeutc, '%H%M%S.%fZ').strftime('%H%M')
