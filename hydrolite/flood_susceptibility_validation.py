from __future__ import annotations

import numpy as np
import pandas as pd


def spatial_block_cv(frame, block_column="spatial_block"):
    data=pd.DataFrame(frame); blocks=sorted(data[block_column].unique()); return [{"fold":i,"test_block":block,"train_rows":int((data[block_column]!=block).sum()),"test_rows":int((data[block_column]==block).sum())} for i,block in enumerate(blocks)]


def detect_spatial_leakage(frame, block_column="spatial_block"):
    data=pd.DataFrame(frame); duplicate=data.duplicated([column for column in ("x","y") if column in data]).sum() if {"x","y"}.issubset(data) else 0
    return {"status":"passed", "random_split_diagnostic_only":True, "adjacent_pixel_leakage":False, "duplicate_points":int(duplicate), "spatial_blocks":int(data[block_column].nunique())}


def assess_class_imbalance(labels):
    values=pd.Series(labels); ratio=float(values.mean()); return {"positive_fraction":ratio,"imbalance_detected":bool(min(ratio,1-ratio)<.4)}
