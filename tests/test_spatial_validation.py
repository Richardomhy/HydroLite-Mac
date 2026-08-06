from hydrolite.flood_susceptibility_features import build_synthetic_flood_features
from hydrolite.flood_susceptibility_validation import assess_class_imbalance, detect_spatial_leakage, spatial_block_cv


def test_spatial_blocks_and_imbalance_diagnostics():
    frame=build_synthetic_flood_features(); assert len(spatial_block_cv(frame))==6 and assess_class_imbalance(frame.flood)["imbalance_detected"] and not detect_spatial_leakage(frame)["adjacent_pixel_leakage"]
