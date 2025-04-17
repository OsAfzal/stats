import ee
import geemap
import pandas as pd
from datetime import datetime


def initialize_ee():
    ee.Initialize()


def region(path):
    return ee.FeatureCollection(path)
def region_geo(roi):
    return roi.geometry()

# Filter Landsat 9 ImageCollection by date, bounds, and cloud cover
def filter_landsat_collection(image, start_date, end_date, region, cloud_thresh=10):
    return ee.ImageCollection(image) \
        .filterDate(start_date, end_date) \
        .filterBounds(region) \
        .filter(ee.Filter.lt('CLOUD_COVER', cloud_thresh))

# Get total number of images
def count_images(collection):
    return collection.size().getInfo()

# Get available WRS path/row combinations
def path_row_combinations(collection):
    paths = collection.aggregate_array('WRS_PATH').getInfo()
    rows = collection.aggregate_array('WRS_ROW').getInfo()
    df = pd.DataFrame({'path': paths, 'row': rows})
    return df.drop_duplicates()

# Get temporal distribution (images per month)
def monthly_distribution(collection):
    def extract_date(image):
        date = ee.Date(image.get('system:time_start')).format('YYYY-MM-dd')
        return ee.Feature(None, {'date': date})
    
    dates = collection.map(extract_date).aggregate_array('date').getInfo()
    df = pd.DataFrame({'date': pd.to_datetime(dates)})
    df['month'] = df['date'].dt.to_period('M')
    return df['month'].value_counts().sort_index()

def image_by_date(collection, target_date_str, days_buffer=20, verbose=True):
    
    target_date = ee.Date(target_date_str)
    buffer_start = target_date.advance(-days_buffer, 'day')
    buffer_end = target_date.advance(days_buffer, 'day')

    filtered = collection.filterDate(buffer_start, buffer_end).sort('system:time_start')

    image = filtered.first()

    # Safely check if an image was found
    if image is None or image.getInfo() is None:
        if verbose:
            print(f"No image found within ±{days_buffer} days of {target_date_str}")
        return None

    if verbose:
        date_ms = image.get('system:time_start').getInfo()
        date_str = datetime.utcfromtimestamp(date_ms / 1000).strftime('%Y-%m-%d')
        print(f"Found image closest to {target_date_str}: {date_str}")

    return image


# Filter collection by WRS path and row
def filter_by_path_row(collection, path, row):
    return collection.filter(ee.Filter.And(
        ee.Filter.eq('WRS_PATH', path),
        ee.Filter.eq('WRS_ROW', row)
    ))

# Joining multiple WRS tiles
def tiles_join(collection, target_date_str, region, days_buffer=10, verbose=True):
    
    target_date = ee.Date(target_date_str)
    buffer_start = target_date.advance(-days_buffer, 'day')
    buffer_end = target_date.advance(days_buffer, 'day')

    # Filter by date and region
    filtered = collection \
        .filterDate(buffer_start, buffer_end) \
        .filterBounds(region)

    count = filtered.size().getInfo()
    if count == 0:
        if verbose:
            print(f"No images found within ±{days_buffer} days of {target_date_str}")
        return None

    # Create median composite to merge overlapping tiles
    composite = filtered.median().clip(region)

    if verbose:
        print(f"Composite image from {count} overlapping scenes within ±{days_buffer} days of {target_date_str}")

    return composite

# Export multi-band image as GeoTIFF to local
def export_multiband_tiff(image, bands, filename, region, scale=30):
    multiband_image = image.select(bands)
    geemap.ee_export_image(
        ee_object=multiband_image,
        filename=filename,
        scale=scale,
        region=region,
        file_per_band=False
    )
    print(f"Exported {filename}")

# Export to Google Drive (optional)
def export_to_drive(image, bands, region, description='landsat_multiband_export', folder='EarthEngine', scale=30):
    multiband_image = image.select(bands)
    task = ee.batch.Export.image.toDrive(
        image=multiband_image,
        description=description,
        folder=folder,
        fileNamePrefix=description,
        region=region,
        scale=scale,
        maxPixels=1e13,
        fileFormat='GeoTIFF',
        formatOptions={'cloudOptimized': True}
    )
    task.start()
    print("Export to Drive started.")
    return task
