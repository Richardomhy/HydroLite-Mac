import numpy as np
from hydrolite.routing import muskingum_route
def test_muskingum_tail_releases_storage():
    out=muskingum_route(np.r_[0.,10.,0.,np.zeros(80)],2,.2,1,'R');assert out[-1]<1e-8
