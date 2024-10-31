import glob, shutil, time, os
from pathlib import Path

"""
##########################################################
User options
"""

#Variable assignment
DEMLayer            = 'C:/Temp/DEM.tif'
iterations          = 160
noiseLevel          = 0.15

#Options for compressing the images, ZSTD has the best speed but LZW is the most compatible
compressOptions         = 'COMPRESS=ZSTD|NUM_THREADS=ALL_CPUS|PREDICTOR=1|ZSTD_LEVEL=1|BIGTIFF=IF_SAFER|TILED=YES'


"""
##########################################################
Variable assignment for processing
"""

#Get the location of the initial image for storage of processing files
rootProcessDirectory = str(Path(DEMLayer).parent.absolute()).replace('\\','/') + '/'

#Set up the layer name for the raster calculations
DEMName = DEMLayer.split("/")
DEMName = DEMName[-1]
DEMName = DEMName[:len(DEMName)-4]
demRas = QgsRasterLayer(DEMLayer) 
pixelSize = (demRas.rasterUnitsPerPixelX() + demRas.rasterUnitsPerPixelY())/2

crs = coordinateSystemRas = demRas.crs().authid()
demRasBounds = demRas.extent() 
xminDemRas = demRasBounds.xMinimum()
xmaxDemRas = demRasBounds.xMaximum()
yminDemRas = demRasBounds.yMinimum()
ymaxDemRas = demRasBounds.yMaximum()
coordsInputRas = "%f, %f, %f, %f" %(xminDemRas, xmaxDemRas, yminDemRas, ymaxDemRas)

#Making a folder for processing each time, to avoid issues with locks
processDirectory = rootProcessDirectory + DEMName + 'Process' + '/'
if not os.path.exists(processDirectory): os.mkdir(processDirectory)



"""
##########################################################
Now a function is defined that contains several steps...
"""


def horizonCalculator(functionInDEM, functionCrs, functionProcessDirectory, functionX, functionCompressOptions, functionPreviousProcessDirectory):


    #A noise raster is created. The purpose of this is to give greater weighting to slopes that are so sloped towards the viewpoint that any noise added is not enough to block the view.
    processing.run("native:createrandomnormalrasterlayer", {'EXTENT':coordsInputRas + ' [' + functionCrs + ']','TARGET_CRS':QgsCoordinateReferenceSystem(functionCrs),'PIXEL_SIZE':pixelSize,'OUTPUT_TYPE':0,'MEAN':0,'STDDEV':noiseLevel,'OUTPUT':functionProcessDirectory + 'RandomRas.tif'})

    processing.run("qgis:rastercalculator", {'EXPRESSION':'\"' + DEMName + '@1\" + \"RandomRas@1\"','LAYERS':[functionProcessDirectory + 'RandomRas.tif', DEMLayer],
        'CELLSIZE':0,'EXTENT':None,'CRS':None,'OUTPUT':functionProcessDirectory + 'DEMPlusNoise.tif'})
        

    

    processing.run("grass7:r.fill.dir", {'input':functionProcessDirectory + 'DEMPlusNoise.tif','format':0,'-f':False,'output':functionProcessDirectory + 'DEMPlusNoiseFilled.tif','direction':'TEMPORARY_OUTPUT','areas':'TEMPORARY_OUTPUT','GRASS_REGION_PARAMETER':None,'GRASS_REGION_CELLSIZE_PARAMETER':0,'GRASS_RASTER_FORMAT_OPT':'','GRASS_RASTER_FORMAT_META':''})


    processing.run("grass7:r.watershed", {'elevation':functionProcessDirectory + 'DEMPlusNoiseFilled.tif','depression':None,'flow':None,'disturbed_land':None,'blocking':None,'threshold':1,
        'max_slope_length':None,'convergence':5,'memory':300,'-s':False,'-m':False,'-4':False,'-a':True,'-b':False,'accumulation':functionProcessDirectory + 'DEMPlusNoiseFilledAccumulated.tif','drainage':'TEMPORARY_OUTPUT','basin':'TEMPORARY_OUTPUT','stream':'TEMPORARY_OUTPUT','half_basin':'TEMPORARY_OUTPUT','length_slope':'TEMPORARY_OUTPUT','slope_steepness':'TEMPORARY_OUTPUT','tci':'TEMPORARY_OUTPUT','spi':'TEMPORARY_OUTPUT','GRASS_REGION_PARAMETER':None,'GRASS_REGION_CELLSIZE_PARAMETER':0,'GRASS_RASTER_FORMAT_OPT':'','GRASS_RASTER_FORMAT_META':''})




    if functionPreviousProcessDirectory == 'not yet':
        processing.run("gdal:rastercalculator", {'INPUT_A':functionProcessDirectory + 'DEMPlusNoiseFilledAccumulated.tif','BAND_A':1,'INPUT_B':None,'BAND_B':None,'INPUT_C':None,'BAND_C':None,'INPUT_D':None,'BAND_D':None,'INPUT_E':None,'BAND_E':None,'INPUT_F':None,'BAND_F':None,
            'FORMULA':'A','NO_DATA':None,'EXTENT_OPT':0,'PROJWIN':None,'RTYPE':5,'OPTIONS':functionCompressOptions,'EXTRA':'','OUTPUT':functionProcessDirectory + 'FlowSoFar.tif'})
    else:
        processing.run("gdal:rastercalculator", {'INPUT_A':functionProcessDirectory + 'DEMPlusNoiseFilledAccumulated.tif','BAND_A':1,'INPUT_B':functionPreviousProcessDirectory + 'FlowSoFar.tif','BAND_B':1,'INPUT_C':None,'BAND_C':None,'INPUT_D':None,'BAND_D':None,'INPUT_E':None,'BAND_E':None,'INPUT_F':None,'BAND_F':None,
            'FORMULA':'A+B','NO_DATA':None,'EXTENT_OPT':0,'PROJWIN':None,'RTYPE':5,'OPTIONS':functionCompressOptions,'EXTRA':'','OUTPUT':functionProcessDirectory + 'FlowSoFar.tif'})


    
    
    
    
    
    
    processing.run("native:slope", {'INPUT':functionProcessDirectory + 'DEMPlusNoise.tif','Z_FACTOR':1,'OUTPUT':functionProcessDirectory + 'Slope.tif'})
    
    
    
    if functionPreviousProcessDirectory == 'not yet':
        processing.run("gdal:rastercalculator", {'INPUT_A':functionProcessDirectory + 'Slope.tif','BAND_A':1,'INPUT_B':None,'BAND_B':None,'INPUT_C':None,'BAND_C':None,'INPUT_D':None,'BAND_D':None,'INPUT_E':None,'BAND_E':None,'INPUT_F':None,'BAND_F':None,
            'FORMULA':'A','NO_DATA':None,'EXTENT_OPT':0,'PROJWIN':None,'RTYPE':5,'OPTIONS':functionCompressOptions,'EXTRA':'','OUTPUT':functionProcessDirectory + 'SlopeSoFar.tif'})
    else:
        processing.run("gdal:rastercalculator", {'INPUT_A':functionProcessDirectory + 'Slope.tif','BAND_A':1,'INPUT_B':functionPreviousProcessDirectory + 'SlopeSoFar.tif','BAND_B':1,'INPUT_C':None,'BAND_C':None,'INPUT_D':None,'BAND_D':None,'INPUT_E':None,'BAND_E':None,'INPUT_F':None,'BAND_F':None,
            'FORMULA':'A+B','NO_DATA':None,'EXTENT_OPT':0,'PROJWIN':None,'RTYPE':5,'OPTIONS':functionCompressOptions,'EXTRA':'','OUTPUT':functionProcessDirectory + 'SlopeSoFar.tif'})


    

    os.remove(functionProcessDirectory + 'RandomRas.tif')
    os.remove(functionProcessDirectory + 'DEMPlusNoise.tif')
    







previousProcessDirectory = 'not yet'

for x1 in range(iterations):

    processContext = QgsProcessingContext()



    
    subProcessDirectory = processDirectory + str(x1) + '/'
    if not os.path.exists(subProcessDirectory): os.mkdir(subProcessDirectory)

    horizonCalculator(DEMLayer, crs, subProcessDirectory, x1, compressOptions, previousProcessDirectory)
    
    previousProcessDirectory = subProcessDirectory
    


processing.run("gdal:rastercalculator", {'INPUT_A':subProcessDirectory + 'SlopeSoFar.tif','BAND_A':1,'INPUT_B':None,'BAND_B':None,'INPUT_C':None,'BAND_C':None,'INPUT_D':None,'BAND_D':None,'INPUT_E':None,'BAND_E':None,'INPUT_F':None,'BAND_F':None,
            'FORMULA':'numpy.tan((A/' + str(iterations) + ')*3.141592/180)','NO_DATA':None,'EXTENT_OPT':0,'PROJWIN':None,'RTYPE':5,'OPTIONS':compressOptions,'EXTRA':'','OUTPUT':processDirectory + 'FinalSlope.tif'})



processing.run("gdal:rastercalculator", {'INPUT_A':subProcessDirectory + 'FlowSoFar.tif','BAND_A':1,'INPUT_B':processDirectory + 'FinalSlope.tif','BAND_B':1,'INPUT_C':None,'BAND_C':None,'INPUT_D':None,'BAND_D':None,'INPUT_E':None,'BAND_E':None,'INPUT_F':None,'BAND_F':None,
            'FORMULA':'log(B/A)','NO_DATA':None,'EXTENT_OPT':0,'PROJWIN':None,'RTYPE':5,'OPTIONS':compressOptions,'EXTRA':'','OUTPUT':processDirectory + 'FinalFlow.tif'})
