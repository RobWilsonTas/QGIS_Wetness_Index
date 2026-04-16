import glob, shutil, time, os
from pathlib import Path
from qgis.core import (QgsProcessingAlgorithm, QgsProcessingParameterRasterLayer, QgsRasterLayer,QgsProject, QgsSingleBandPseudoColorRenderer, QgsRasterShader,
    QgsColorRampShader, Qgis, QgsProcessingParameterNumber, QgsCoordinateReferenceSystem)
from qgis import processing
from PyQt5.QtGui import QColor
import numpy as np
from osgeo import gdal
from scipy.ndimage import minimum_filter

#Define the class to grab the qgsprocessing stuff
class QGISWetnessIndex(QgsProcessingAlgorithm):

    def initAlgorithm(self, config=None):
        
        #Get the user's DEM
        self.addParameter(QgsProcessingParameterRasterLayer(
            "inputRaster","Select your elevation model below", defaultValue=None, optional=False))
        
        #Ask how many iterations they want to do
        self.addParameter(QgsProcessingParameterNumber(
            "iterations","Number of iterations (best start small)",type=QgsProcessingParameterNumber.Integer,defaultValue=1,minValue=1))
        
        #Ask how much noise to apply to the DEM
        self.addParameter(QgsProcessingParameterNumber(
            "noiseLevel","Noise level (how much the DEM shifts per iteration) in metres",type=QgsProcessingParameterNumber.Double,defaultValue=0.15,minValue=0.001))

    def processAlgorithm(self, parameters, context, feedback):
        try:
            
            #Bring in the user's parameters
            inputDEMLayer = self.parameterAsRasterLayer(parameters, "inputRaster", context)
            if not inputDEMLayer or not inputDEMLayer.isValid():
                feedback.reportError("Input raster is invalid")
                return {}
            iterations = self.parameterAsInt(parameters, "iterations", context)
            noiseLevel = self.parameterAsDouble(parameters, "noiseLevel", context)

            #Options for compressing the images, ZSTD has the best speed but LZW is the most compatible
            compressOptions     = 'COMPRESS=ZSTD|NUM_THREADS=ALL_CPUS|PREDICTOR=1|ZSTD_LEVEL=1|BIGTIFF=IF_SAFER|TILED=YES'

            """
            ##########################################################
            Variable assignment for processing
            """

            #Get the location of the initial image for storage of processing files
            inputDEMLayerPath = inputDEMLayer.dataProvider().dataSourceUri()
            rootProcessDirectory = os.path.dirname(inputDEMLayerPath).replace('\\','/') + '/'

            #Set up the layer name for the raster calculations
            DEMName = Path(inputDEMLayer.dataProvider().dataSourceUri()).stem
            pixelSize = (inputDEMLayer.rasterUnitsPerPixelX() + inputDEMLayer.rasterUnitsPerPixelY())/2

            #Get a few attributes from the raster
            coordinateSystemRas = inputDEMLayer.crs().authid()
            inputDEMLayerBounds = inputDEMLayer.extent()
            coordsInputRas = str(inputDEMLayerBounds.xMinimum()) + ", " + str(inputDEMLayerBounds.xMaximum()) + ", " + str(inputDEMLayerBounds.yMinimum()) + ", " + str(inputDEMLayerBounds.yMaximum())

            """
            ################################################################################################
            Calculate the slope using a smoothed DEM to reduce noise
            """

            #Reduce resolution of the DEM
            reducedResDEM = processing.run("gdal:warpreproject", {'INPUT': inputDEMLayer, 'SOURCE_CRS': None, 'TARGET_CRS': None, 'RESAMPLING': 3, 'NODATA': None,
                'TARGET_RESOLUTION': None, 'OPTIONS': compressOptions, 'DATA_TYPE': 0, 'TARGET_EXTENT': None, 'TARGET_EXTENT_CRS': coordinateSystemRas,
                'MULTITHREADING': True, 'EXTRA': '-tr ' + str(inputDEMLayer.rasterUnitsPerPixelX()*2) + ' ' + str(inputDEMLayer.rasterUnitsPerPixelX()*2),
                'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

            #Bring back the res with resampling
            smoothedDEM = processing.run("gdal:warpreproject", {'INPUT': reducedResDEM,'SOURCE_CRS': None, 'TARGET_CRS': None, 'RESAMPLING': 3, 'NODATA': None, 'TARGET_RESOLUTION': None,
                'OPTIONS': compressOptions, 'DATA_TYPE': 0,'TARGET_EXTENT': inputDEMLayer.extent(), 'TARGET_EXTENT_CRS': coordinateSystemRas, 'MULTITHREADING': True,
                'EXTRA': '-tr ' + str(inputDEMLayer.rasterUnitsPerPixelX()) + ' ' + str(inputDEMLayer.rasterUnitsPerPixelX()),'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

            #Get the slope
            smoothedDEMSlope = processing.run("gdal:slope", {'INPUT':smoothedDEM,'BAND':1,'SCALE':1,'AS_PERCENT':False,'COMPUTE_EDGES':True,
                'ZEVENBERGEN':False,'OPTIONS':None,'EXTRA':'','OUTPUT':'TEMPORARY_OUTPUT'})['OUTPUT']

            """
            ##########################################################################################
            Running the flow accumulation repeatedly
            """
                
            flowSoFarLayer = None
            for x in range(iterations):

                #Create a random noise raster matching the DEM extent and CRS
                #This is used to perturb the DEM slightly
                randomRaster = processing.run("native:createrandomnormalrasterlayer", {'EXTENT':coordsInputRas + ' [' + coordinateSystemRas + ']',
                    'TARGET_CRS':QgsCoordinateReferenceSystem(coordinateSystemRas), 'PIXEL_SIZE':pixelSize, 'OUTPUT_TYPE':0, 'MEAN':0,'STDDEV':noiseLevel,
                    'OUTPUT':'TEMPORARY_OUTPUT'})['OUTPUT']

                #Add the random noise raster to the DEM to get a DEM with bumped around height values
                demPlusNoise = processing.run("gdal:rastercalculator", {'INPUT_A':randomRaster,'BAND_A':1, 'INPUT_B':inputDEMLayer,'BAND_B':1,
                    'FORMULA':'A+B','RTYPE':5, 'OUTPUT':'TEMPORARY_OUTPUT'})['OUTPUT']

                #Fill sinks/depressions in the noisy DEM using GRASS r.fill.dir
                #This ensures hydrological continuity
                demPlusNoiseFilledPath = processing.run("grass7:r.fill.dir", {'input':demPlusNoise,'format':0,'-f':False,
                    'output':'TEMPORARY_OUTPUT','direction':'TEMPORARY_OUTPUT', 'areas':'TEMPORARY_OUTPUT','GRASS_REGION_PARAMETER':None,
                    'GRASS_REGION_CELLSIZE_PARAMETER':0,'GRASS_RASTER_FORMAT_OPT':'','GRASS_RASTER_FORMAT_META':''})['output']
                demPlusNoiseFilledLayer = QgsRasterLayer(demPlusNoiseFilledPath, "DEMPlusNoiseFilled")

                #Calculate flow accumulation using GRASS r.watershed
                #Produces raster of accumulated flow at each cell
                demAccumulatedPath = processing.run("grass7:r.watershed", {'elevation':demPlusNoiseFilledLayer,'depression':None,'flow':None,'disturbed_land':None,
                'blocking':None,'threshold':1,'max_slope_length':None,'convergence':5,'memory':300,'-s':False,'-m':False,'-4':False,'-a':True,'-b':False,
                    'accumulation':'TEMPORARY_OUTPUT','drainage':'TEMPORARY_OUTPUT','basin':'TEMPORARY_OUTPUT','stream':'TEMPORARY_OUTPUT','half_basin':'TEMPORARY_OUTPUT',
                    'length_slope':'TEMPORARY_OUTPUT','slope_steepness':'TEMPORARY_OUTPUT','tci':'TEMPORARY_OUTPUT','spi':'TEMPORARY_OUTPUT',
                    'GRASS_REGION_PARAMETER':None,'GRASS_REGION_CELLSIZE_PARAMETER':0, 'GRASS_RASTER_FORMAT_OPT':'','GRASS_RASTER_FORMAT_META':''})['accumulation']
                demAccumulatedLayer = QgsRasterLayer(demAccumulatedPath, "DEMAccumulated")

                #If this is the first iteration then we just make a copy of the current accumulation raster
                if not flowSoFarLayer:
                    flowSoFarLayer = processing.run("gdal:rastercalculator", {'INPUT_A':demAccumulatedLayer,'BAND_A':1,'FORMULA':'A','NO_DATA':None,'EXTENT_OPT':0,
                        'PROJWIN':None,'RTYPE':5,'OPTIONS':compressOptions,'EXTRA':'', 'OUTPUT':'TEMPORARY_OUTPUT'})['OUTPUT']
                
                #Subsequent iterations: add current accumulation raster to the accumulation so far
                else:
                    flowSoFarLayer = processing.run("gdal:rastercalculator", {'INPUT_A':demAccumulatedLayer, 'BAND_A':1,'INPUT_B':flowSoFarLayer,'BAND_B':1,
                        'FORMULA':'A+B','NO_DATA':None,'EXTENT_OPT':0,'PROJWIN':None,'RTYPE':5,'OPTIONS':compressOptions,
                        'EXTRA':'','OUTPUT':'TEMPORARY_OUTPUT'})['OUTPUT']

            #The wetness follows this formula: log(flowAccumulation / tan(slope))  https://en.wikipedia.org/wiki/Topographic_wetness_index
            wetnessLayerPath = processing.run("gdal:rastercalculator", {'INPUT_A':flowSoFarLayer,'BAND_A':1,'INPUT_B':smoothedDEMSlope,'BAND_B':1,
                'FORMULA':'log(A/((numpy.tan(numpy.deg2rad(B))+0.1))/' + str(iterations) + ')','NO_DATA':None,
                'EXTENT_OPT':0,'PROJWIN':None,'RTYPE':5,'OPTIONS':compressOptions,'EXTRA':'','OUTPUT':'TEMPORARY_OUTPUT'})['OUTPUT']
            wetnessLayer = QgsRasterLayer(wetnessLayerPath, "Wetness Index")
                
            """
            #######################################################################
            Spreading wetness across flat areas
            """
            
            #Turn the layers into numpy arrays
            wetnessDataset = gdal.Open(wetnessLayer.source())
            wetnessGrid = wetnessDataset.GetRasterBand(1).ReadAsArray()
            demDataset = gdal.Open(inputDEMLayer.source())
            elevationGrid = demDataset.GetRasterBand(1).ReadAsArray()

            #Variables that can be adjusted if we want different behaviour
            pixelSizeMeters = 10
            neighbourhoodSizePixels = 8
            halfWindow = neighbourhoodSizePixels // 2

            #Build the neighbourhood offsets we use for scanning around each cell within the numpy array
            yOffsets, xOffsets = np.meshgrid(
                np.arange(-halfWindow, halfWindow + 1),
                np.arange(-halfWindow, halfWindow + 1),
                indexing='ij')
            offsetPairs = np.stack([yOffsets.ravel(), xOffsets.ravel()], axis=1)

            #Pad the wetness grid so edges don't break the neighbourhood search
            rows, cols = wetnessGrid.shape
            paddedWetness = np.pad(wetnessGrid, halfWindow, mode='edge')

            #Find the strongest nearby wetness value with distance decay applied
            bestWetness = np.full(wetnessGrid.shape, -np.inf)

            #Shift the entire grid around in different offsets to find the most significant close wetness
            for yOffset, xOffset in offsetPairs:
                distanceMeters = np.sqrt(yOffset**2 + xOffset**2) * pixelSizeMeters
                shiftedWetness = paddedWetness[
                    halfWindow + yOffset:halfWindow + yOffset + rows,
                    halfWindow + xOffset:halfWindow + xOffset + cols]

                #The -0.025 here controls how much the further pixels are devalued for being far away
                decayedWetness = shiftedWetness * np.exp(-0.025 * distanceMeters)
                updateMask = decayedWetness > bestWetness
                bestWetness[updateMask] = decayedWetness[updateMask]

            #Find local low points in the terrain surface
            localLowPoints = minimum_filter(elevationGrid, size=neighbourhoodSizePixels, mode='nearest')
            heightAboveLowPoints = np.maximum(elevationGrid - localLowPoints, 0)

            #Combine wetness signal with terrain penalty
            finalWetnessArray = np.maximum(bestWetness * np.exp(-0.25 * heightAboveLowPoints), wetnessGrid)

            #Prep some stuff to turn a numpy array into a memory raster layer
            gridRowCount, gridColumnCount = finalWetnessArray.shape
            geoTransformMatrixForRaster = [inputDEMLayerBounds.xMinimum(), inputDEMLayerBounds.width() / gridColumnCount, 0,
                inputDEMLayerBounds.yMaximum(), 0, -inputDEMLayerBounds.height() / gridRowCount]
            temporaryRasterFilePath = "/vsimem/" + "Final wetness" + ".tif"
            geoTiffDriverForRasterWriting = gdal.GetDriverByName("GTiff")

            #Actually turn a numpy array into a memory raster layer
            geoTiffDatasetBeingBuilt = geoTiffDriverForRasterWriting.Create(temporaryRasterFilePath, gridColumnCount, gridRowCount, 1, gdal.GDT_Float32)
            geoTiffDatasetBeingBuilt.SetGeoTransform(geoTransformMatrixForRaster)
            geoTiffDatasetBeingBuilt.SetProjection(inputDEMLayer.crs().toWkt())
            geoTiffDatasetBeingBuilt.GetRasterBand(1).WriteArray(finalWetnessArray)
            geoTiffDatasetBeingBuilt.FlushCache()
            geoTiffDatasetBeingBuilt = None

            """
            #######################################################################
            Styling
            """

            #Add in the wetness layer
            finalWetnessLayer = QgsRasterLayer(temporaryRasterFilePath, "Final wetness")
            QgsProject.instance().addMapLayer(finalWetnessLayer)

            #Begin creating a colour ramp
            colorRampShader = QgsColorRampShader()
            colorRampShader.setColorRampType(QgsColorRampShader.Interpolated)
            colorRampShader.setMinimumValue(0)
            colorRampShader.setMaximumValue(18.5)

            #Decide on what numbers correspond to what colours
            colorRampItems = [QgsColorRampShader.ColorRampItem(0.0, QColor('#ffe5de')),
                QgsColorRampShader.ColorRampItem(3.6, QColor('#fee385')),
                QgsColorRampShader.ColorRampItem(7.2, QColor('#66fa48')),
                QgsColorRampShader.ColorRampItem(10.9, QColor('#02bcaa')),
                QgsColorRampShader.ColorRampItem(14.5, QColor('#002ede')),
                QgsColorRampShader.ColorRampItem(18.5, QColor('#1f0495'))]
            colorRampShader.setColorRampItemList(colorRampItems)

            #Apply the colouring
            rasterShader = QgsRasterShader()
            rasterShader.setRasterShaderFunction(colorRampShader)
            renderer = QgsSingleBandPseudoColorRenderer(finalWetnessLayer.dataProvider(), 1, rasterShader)
            finalWetnessLayer.setRenderer(renderer)
            finalWetnessLayer.triggerRepaint()

            """
            ############################################################################################
            Final stuff
            """
        
        except BaseException as e:
            broItCrashed
            
        #Return nothing because you need to return something
        return {}

    #Required bs
    def name(self): return 'qgis_wetness_index'
    def displayName(self): return 'QGIS Wetness Index'
    def group(self): return 'Custom Scripts'
    def groupId(self): return 'customscripts'
    def createInstance(self): return QGISWetnessIndex()
