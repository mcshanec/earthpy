import contextlib
import os
import rasterio as rio
import numpy as np
from shapely.geometry import mapping, box

def extent_to_json(left, right, bottom, top):
    """Convert bounds to a shapely geojson like spatial object.
    Helper function
    This format is what shapely uses. The output object can be used
    to crop a raster image.

    Parameters
    ----------
    left, right, bottom, top : numbers
    The left, right top corner coordinates of the extent to be used for cropping.
    Return
    ----------
    extent_json : dict
    A dictionary of corner coordinates for the new extent
    """
    extent_json = mapping(box(left, right, bottom, top))
    return extent_json

# calculate normalized difference between two arrays
# both arrays must be of the same size
def normalized_diff(b1, b2):
    """Take two numpy arrays and calculate the normalized difference
    Math will be calculated (b2-b1) / (b2+b1).

    Parameters
    ----------
    b1, b2 : arrays with the same shape
        Math will be calculated (b2-b1) / (b2+b1).
    """
    if not (b1.shape == b2.shape):
        raise ValueError("Both arrays should be of the same dimensions")

    n_diff = (b2 - b1) / (b2 + b1)
    #ndvi[np.isnan(ndvi)] = 0
    n_diff = np.ma.masked_invalid(n_diff)
    return n_diff


# EL function
# we probably want to include a no data value here if provided ...
def stack_raster_tifs(band_paths, out_path):
    """Take a list of raster paths and turn into an ouput raster stack.
    Note that this function depends upon the stack() function to be submitted to rasterio.
    but the stack function ins't stand alone as written

    Parameters
    ----------
    band_paths : list of file paths
        A list with paths to the bands you wish to stack. Bands
        will be stacked in the order given in this list.
    out_path : string
        A path for the output stacked raster file.
    """
    # set default import to read
    kwds = {'mode': 'r'}

    if not os.path.exists(os.path.dirname(out_path)):
        raise ValueError("The output directory path that you provided does not exist")

    # the with statement ensures that all files are closed at the end of the with statement
    with contextlib.ExitStack() as context:
        sources = [context.enter_context(rio.open(path, **kwds)) for path in band_paths]

        dest_kwargs = sources[0].meta
        dest_count = sum(src.count for src in sources)
        dest_kwargs['count'] = dest_count

        # save out a stacked gtif file
        with rio.open(out_path, 'w', **dest_kwargs) as dest:
            return stack(sources, dest)


# function to be submitted to rasterio
# add unit tests: some are here: https://github.com/mapbox/rasterio/blob/master/rasterio/mask.py
# this function doesn't stand alone because it writes to a open object called in the other function.
def stack(sources, dest):
    """Stack a set of bands into a single file.

    Parameters
    ----------
    sources : list of rasterio dataset objects
        A list with paths to the bands you wish to stack. Objects
        will be stacked in the order provided in this list.
    dest : a rio.open writable object that will store raster data.
    """

    #if not os.path.exists(os.path.dirname(dest)):
    #    raise ValueError("The output directory path that you provided does not exist")

    if not type(sources[0]) == rio._io.RasterReader:
        raise ValueError("The sources object should be of type: rasterio.RasterReader")

    for ii, ifile in enumerate(sources):
            bands = sources[ii].read()
            if bands.ndim != 3:
                bands = bands[np.newaxis, ...]
            for band in bands:
                dest.write(band, ii+1)


def crop_image(raster, geoms):
    """Crop a single file using geometry objects.

    Parameters
    ----------
    raster : rasterio object
        The rasterio object to be cropped. Ideally this object is opened in a
        scontext manager to ensure the file is properly closed.
    geoms : list of polygons
        Polygons are GeoJSON-like dicts specifying the boundaries of features
        in the raster to be kept. All data outside of specified polygons
        will be set to nodata.

    Returns
    ----------
    out_image: masked numpy array
        A masked numpy array that is masked / cropped to the geoms object extent
    out_meta:  dict
        A dictionary containing the updated metadata for the cropped raster.
        Specifically the extent (shape elements) and transform properties are updated.
    """

    if not type(geoms) == list:
        raise ValueError("The geoms element used to crop the raster needs to be of type: list. If it is of type dictionary, you can simpy add [object-name-here] to turn it into a list.")

    # Mask the input image and update the metadata
    #with rio.open(path) as src:
    out_image, out_transform = rio.mask.mask(raster, geoms, crop = True)
    out_meta = raster.meta.copy()
    out_meta.update({"driver": "GTiff",
                    "height": out_image.shape[1],
                    "width": out_image.shape[2],
                    "transform": out_transform})
    return (out_image, out_meta)


def bytescale(data, cmin=None, cmax=None, high=255, low=0):
    """
    Code from the original scipy package to resolve non 8 bit images to 8 bit for easy plotting
    Note that this will scale values <0 to 0 and values >255 to 255

    Parameters
    ----------
    data : numpy array
        The dataset to be scaled.
    cmin : number
        minvalue in the dataset. by default set to data.min()
    cmax : maxvalue in the dataset. by default set to data.min()

    """
    if high > 255:
        raise ValueError("`high` should be less than or equal to 255.")
    if low < 0:
        raise ValueError("`low` should be greater than or equal to 0.")
    if high < low:
        raise ValueError("`high` should be greater than or equal to `low`.")

    if cmin is None:
        cmin = data.min()
    if cmax is None:
        cmax = data.max()
    cscale = cmax - cmin
    if cscale < 0:
        raise ValueError("`cmax` should be larger than `cmin`.")
    elif cscale == 0:
        cscale = 1
    scale = float(high - low) / cscale
    bytedata = (data - cmin) * scale + low
    return (bytedata.clip(low, high) + 0.5).astype(np.int8)




# scale an input array-like to a mininum and maximum number
# the input array must be of a floating point array
# if you have a non-floating point array, convert to floating using `astype('float')`
# this works with n-dimensional arrays
# it will mutate in place
# min and max can be integers
# may end up deprecating this
def scale_range (input_array, min, max, clip=True):
    # coerce to float if int
    if input_array.dtype == "int":
        input_array = input_array.astype(np.float16)

    input_array += -(np.min(input_array))
    input_array /= np.max(input_array) / (max - min)
    input_array += min
    # if the data have negative values that the user wishes to clip, clip them
    if clip:
        input_array.clip(min, max)
    return ((input_array+ 0.5).astype(np.int8))