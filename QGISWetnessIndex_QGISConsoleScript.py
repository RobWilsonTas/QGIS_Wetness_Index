import glob, shutil, time, os
from pathlib import Path

"""
##########################################################
User options
"""

#Variable assignment
DEMLayer            = "C:/Temp/DEM.tif"
iterations          = 10
noiseLevel          = 0.15

#Options for compressing the images, ZSTD has the best speed but LZW is the most compatible
compressOptions     = 'COMPRESS=ZSTD|NUM_THREADS=ALL_CPUS|PREDICTOR=1|ZSTD_LEVEL=1|BIGTIFF=IF_SAFER|TILED=YES'

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

#Get a few attributes from the raster
coordinateSystemRas = demRas.crs().authid()
demRasBounds = demRas.extent() 
xminDemRas = demRasBounds.xMinimum()
xmaxDemRas = demRasBounds.xMaximum()
yminDemRas = demRasBounds.yMinimum()
ymaxDemRas = demRasBounds.yMaximum()
coordsInputRas = "%f, %f, %f, %f" %(xminDemRas, xmaxDemRas, yminDemRas, ymaxDemRas)

#Making a folder for processing
processDirectory = rootProcessDirectory + DEMName + 'Process' + '/'
if not os.path.exists(processDirectory): os.mkdir(processDirectory)

"""
################################################################################################
Calculate the slope using a smoothed DEM to reduce noise
"""

#Reduce res of the DEM
reducedResDEM = processing.run("gdal:warpreproject", {'INPUT': DEMLayer, 'SOURCE_CRS': None, 'TARGET_CRS': None, 'RESAMPLING': 3, 'NODATA': None,
    'TARGET_RESOLUTION': None, 'OPTIONS': compressOptions,
    'DATA_TYPE': 0, 'TARGET_EXTENT': None, 'TARGET_EXTENT_CRS': coordinateSystemRas,
    'MULTITHREADING': True, 'EXTRA': '-tr ' + str(demRas.rasterUnitsPerPixelX()*2) + ' ' + str(demRas.rasterUnitsPerPixelX()*2),
    'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

#Bring back the res with resampling
smoothedDEM = processing.run("gdal:warpreproject", {'INPUT': reducedResDEM,
    'SOURCE_CRS': None, 'TARGET_CRS': None, 'RESAMPLING': 3, 'NODATA': None, 'TARGET_RESOLUTION': None,
    'OPTIONS': compressOptions, 'DATA_TYPE': 0,
    'TARGET_EXTENT': demRas.extent(), 'TARGET_EXTENT_CRS': coordinateSystemRas, 'MULTITHREADING': True,
    'EXTRA': '-tr ' + str(demRas.rasterUnitsPerPixelX()) + ' ' + str(demRas.rasterUnitsPerPixelX()),
    'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

#Get the slope
processing.run("gdal:slope", {'INPUT':smoothedDEM,'BAND':1,'SCALE':1,'AS_PERCENT':False,'COMPUTE_EDGES':False,
    'ZEVENBERGEN':False,'OPTIONS':None,'EXTRA':'','OUTPUT':processDirectory + 'FinalSlope.tif'})

"""
##########################################################
Now a function is defined for calculating flow accumulation
"""

def flowAccumulationCalculator(functionInDEM, functionCrs, functionProcessDirectory, functionX, functionCompressOptions, functionPreviousProcessDirectory):

    #Create a random noise raster matching the DEM extent and CRS
    #This is used to perturb the DEM slightly
    processing.run("native:createrandomnormalrasterlayer", {'EXTENT':coordsInputRas + ' [' + functionCrs + ']',
        'TARGET_CRS':QgsCoordinateReferenceSystem(functionCrs),'PIXEL_SIZE':pixelSize,'OUTPUT_TYPE':0,
        'MEAN':0,'STDDEV':noiseLevel,'OUTPUT':functionProcessDirectory + 'RandomRas.tif'})

    #Add the random noise raster to the DEM to get a DEM with bumped around height values
    processing.run("qgis:rastercalculator", {'EXPRESSION':'\"' + DEMName + '@1\" + \"RandomRas@1\"',
        'LAYERS':[functionProcessDirectory + 'RandomRas.tif', DEMLayer],'CELLSIZE':0,'EXTENT':None,'CRS':None,
        'OUTPUT':functionProcessDirectory + 'DEMPlusNoise.tif'})

    #Fill sinks/depressions in the noisy DEM using GRASS r.fill.dir
    #This ensures hydrological continuity
    processing.run("grass7:r.fill.dir", {'input':functionProcessDirectory + 'DEMPlusNoise.tif','format':0,
        '-f':False,'output':functionProcessDirectory + 'DEMPlusNoiseFilled.tif','direction':'TEMPORARY_OUTPUT',
        'areas':'TEMPORARY_OUTPUT','GRASS_REGION_PARAMETER':None,'GRASS_REGION_CELLSIZE_PARAMETER':0,
        'GRASS_RASTER_FORMAT_OPT':'','GRASS_RASTER_FORMAT_META':''})

    #Calculate flow accumulation using GRASS r.watershed
    #Produces raster of accumulated flow at each cell
    processing.run("grass7:r.watershed", {'elevation':functionProcessDirectory + 'DEMPlusNoiseFilled.tif',
        'depression':None,'flow':None,'disturbed_land':None,'blocking':None,'threshold':1,'max_slope_length':None,
        'convergence':5,'memory':300,'-s':False,'-m':False,'-4':False,'-a':True,'-b':False,
        'accumulation':functionProcessDirectory + 'DEMPlusNoiseFilledAccumulated.tif','drainage':'TEMPORARY_OUTPUT',
        'basin':'TEMPORARY_OUTPUT','stream':'TEMPORARY_OUTPUT','half_basin':'TEMPORARY_OUTPUT',
        'length_slope':'TEMPORARY_OUTPUT','slope_steepness':'TEMPORARY_OUTPUT','tci':'TEMPORARY_OUTPUT',
        'spi':'TEMPORARY_OUTPUT','GRASS_REGION_PARAMETER':None,'GRASS_REGION_CELLSIZE_PARAMETER':0,
        'GRASS_RASTER_FORMAT_OPT':'','GRASS_RASTER_FORMAT_META':''})

    # Combine flow accumulation with previous iteration if it exists
    if functionPreviousProcessDirectory == 'not yet':
        #First iteration: just copy current accumulation
        processing.run("gdal:rastercalculator", {'INPUT_A':functionProcessDirectory + 'DEMPlusNoiseFilledAccumulated.tif',
            'BAND_A':1,'INPUT_B':None,'BAND_B':None,'INPUT_C':None,'BAND_C':None,'INPUT_D':None,'BAND_D':None,
            'INPUT_E':None,'BAND_E':None,'INPUT_F':None,'BAND_F':None,'FORMULA':'A','NO_DATA':None,'EXTENT_OPT':0,
            'PROJWIN':None,'RTYPE':5,'OPTIONS':functionCompressOptions,'EXTRA':'',
            'OUTPUT':functionProcessDirectory + 'FlowSoFar.tif'})
    else:
        #Subsequent iterations: add previous accumulation to current
        processing.run("gdal:rastercalculator", {'INPUT_A':functionProcessDirectory + 'DEMPlusNoiseFilledAccumulated.tif',
            'BAND_A':1,'INPUT_B':functionPreviousProcessDirectory + 'FlowSoFar.tif','BAND_B':1,'INPUT_C':None,
            'BAND_C':None,'INPUT_D':None,'BAND_D':None,'INPUT_E':None,'BAND_E':None,'INPUT_F':None,'BAND_F':None,
            'FORMULA':'A+B','NO_DATA':None,'EXTENT_OPT':0,'PROJWIN':None,'RTYPE':5,'OPTIONS':functionCompressOptions,
            'EXTRA':'','OUTPUT':functionProcessDirectory + 'FlowSoFar.tif'})

    #Clean up noisy rasters to save space
    os.remove(functionProcessDirectory + 'RandomRas.tif')
    os.remove(functionProcessDirectory + 'DEMPlusNoise.tif')

"""
##########################################################################################
Running the flow accumulation function repeatedly
"""

#First iteration
previousProcessDirectory = 'not yet'

for x in range(iterations):

    #Create a new QGIS processing context for each iteration for some reason
    processContext = QgsProcessingContext()

    #Make a subfolder for this iteration
    subProcessDirectory = processDirectory + str(x) + '/'
    if not os.path.exists(subProcessDirectory): os.mkdir(subProcessDirectory)

    #Run the flow accumulation calculator for this iteration
    flowAccumulationCalculator(DEMLayer, coordinateSystemRas, subProcessDirectory, x, compressOptions, previousProcessDirectory)

    #Update reference to previous iteration folder
    previousProcessDirectory = subProcessDirectory

#Final flow calculation: log-transformed ratio of final slope to accumulated flow
processing.run("gdal:rastercalculator", {'INPUT_A':subProcessDirectory + 'FlowSoFar.tif','BAND_A':1,
    'INPUT_B':processDirectory + 'FinalSlope.tif','BAND_B':1,'INPUT_C':None,'BAND_C':None,'INPUT_D':None,
    'BAND_D':None,'INPUT_E':None,'BAND_E':None,'INPUT_F':None,'BAND_F':None,'FORMULA':'log(A/((numpy.tan(numpy.deg2rad(B))+0.1))/' + str(iterations) + ')','NO_DATA':None,
    'EXTENT_OPT':0,'PROJWIN':None,'RTYPE':5,'OPTIONS':compressOptions,'EXTRA':'','OUTPUT':processDirectory + 'FinalWetness.tif'})
    
    
"""
#######################################################################
Styling
"""

#Add in the wetness layer
wetnessLayer = QgsRasterLayer(processDirectory + 'FinalWetness.tif', 'FinalWetness')
QgsProject.instance().addMapLayer(wetnessLayer)

#Begin creating a colour ramp
colorRampShader = QgsColorRampShader()
colorRampShader.setColorRampType(QgsColorRampShader.Interpolated)
colorRampShader.setMinimumValue(0)
colorRampShader.setMaximumValue(18.5)

#Decide on what numbers correspond to what colours
colorRampItems = [
    QgsColorRampShader.ColorRampItem(0.0, QColor('#ffe5de')),
    QgsColorRampShader.ColorRampItem(3.6, QColor('#fee385')),
    QgsColorRampShader.ColorRampItem(7.2, QColor('#66fa48')),
    QgsColorRampShader.ColorRampItem(10.9, QColor('#02bcaa')),
    QgsColorRampShader.ColorRampItem(14.5, QColor('#002ede')),
    QgsColorRampShader.ColorRampItem(18.5, QColor('#1f0495'))]
colorRampShader.setColorRampItemList(colorRampItems)

#Apply the colouring
rasterShader = QgsRasterShader()
rasterShader.setRasterShaderFunction(colorRampShader)
renderer = QgsSingleBandPseudoColorRenderer(wetnessLayer.dataProvider(), 1, rasterShader)
wetnessLayer.setRenderer(renderer)
wetnessLayer.triggerRepaint()
