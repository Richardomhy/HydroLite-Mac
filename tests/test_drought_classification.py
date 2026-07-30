import pandas as pd

from hydrolite.drought_classification import classify_drought_components, classify_drought_value


def test_diagnostic_drought_classification_keeps_components():
    assert classify_drought_value(-2.1)=="extreme_drought"
    result=classify_drought_components(pd.DataFrame({"SPI":[-2,0],"SSI":[-1,1]}))
    assert {"SPI","SSI","SPI_class","SSI_class"}<=set(result)
    assert result.attrs["threshold_source"]=="diagnostic_default_thresholds"
