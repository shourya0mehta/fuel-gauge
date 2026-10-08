import numpy as np
import pytest

from fuelgauge.camera import Camera


@pytest.mark.parametrize("k1", [0.0, 0.08, -0.05])
def test_pixel_direction_round_trip(k1):
    cam = Camera(1536, 1024, yaw=91.3, pitch=-2.0, roll=1.1, hfov=101.0, k1=k1)
    u, v = np.meshgrid(np.linspace(10, 1526, 25), np.linspace(10, 1014, 17))
    az, el = cam.pixel_to_dir(u, v)
    u2, v2 = cam.dir_to_pixel(az, el)
    assert np.allclose(u, u2, atol=1e-6) and np.allclose(v, v2, atol=1e-6)


def test_centre_pixel_looks_along_axis():
    cam = Camera(1000, 800, yaw=250.0, pitch=-3.5, roll=0.0, hfov=90.0)
    az, el = cam.pixel_to_dir(500, 400)
    assert abs(az - 250.0) < 1e-9 and abs(el + 3.5) < 1e-9


def test_edge_of_image_spans_half_fov_without_distortion():
    cam = Camera(1000, 800, yaw=0.0, pitch=0.0, roll=0.0, hfov=100.0, k1=0.0)
    az, el = cam.pixel_to_dir(1000, 400)
    assert abs(az - 50.0) < 1e-6 and abs(el) < 1e-9
    assert abs(cam.effective_hfov() - 100.0) < 1e-9


def test_positive_k1_widens_the_view():
    assert Camera(1536, 1024, hfov=101, k1=0.08).effective_hfov() > 101
