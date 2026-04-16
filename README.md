This python script runs in QGIS and takes a tif DEM to calculate a wetness index

The wetness index is set up to be stochastic, and you can adjust the number of iterations, as well as the noise level added to each iteration

Each iteration works by adding noise to the DEM, removing sinks, and running flow accumulation 

It takes an average of the flow accumulation from the iterations and puts its through a formula to get the index

Finally, it spreads the index out a little around flat areas next to large rivers, to simulate the effect of streams on the water table

Any issues let me know
