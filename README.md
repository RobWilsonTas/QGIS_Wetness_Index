This python script runs in QGIS and takes a tif DEM to calculate a wetness index

The wetness index is set up to be stochasitc, and you can adjust the number of iterations, as well as the noise level added to each iteration

Each iteration works by adding noise to the DEM, removing sinks, and running flow accumulation 

At the end it takes an average of the flow accumulation (as well as the slope)

Finally it puts these outputs through a formula to get the index

Any issues let me know
