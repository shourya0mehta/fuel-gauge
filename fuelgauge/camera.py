"""Camera model for fixed outdoor cameras: equidistant fisheye with one radial term.

A pixel (u, v) maps to a viewing direction (azimuth, elevation) given
    yaw    - azimuth of the optical axis, degrees clockwise from north
    pitch  - tilt of the optical axis above the horizon, degrees
    roll   - rotation about the optical axis, degrees
    hfov   - angle spanned by the image half-width times two, in the undistorted model, degrees
    k1     - radial term: off-axis angle = (r / f) * (1 + k1 * (r / f)^2)

Wildfire cameras (Mobotix, Axis) are strongly barrel-distorted, so a pinhole model does not fit them.
With k1 = 0 and a narrow field of view this reduces to a close approximation of a pinhole camera.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import math
import numpy as np


@dataclass
class Camera:
    width: int
    height: int
    yaw: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0
    hfov: float = 100.0
    k1: float = 0.0

    @property
    def focal(self) -> float:
        """Pixels per radian of the undistorted angle."""
        return (self.width / 2) / math.radians(self.hfov / 2)

    def params(self) -> list[float]:
        return [self.yaw, self.pitch, self.roll, self.hfov, self.k1]

    def with_params(self, p) -> "Camera":
        return Camera(self.width, self.height, *[float(x) for x in p])

    def to_dict(self) -> dict:
        return asdict(self)

    # ------------------------------------------------------------------ pixel -> direction
    def pixel_to_dir(self, u, v):
        """Pixels -> (azimuth deg, elevation deg)."""
        u = np.asarray(u, float); v = np.asarray(v, float)
        dx = u - self.width / 2; dy = -(v - self.height / 2)
        r = np.hypot(dx, dy) / self.focal
        theta = r * (1 + self.k1 * r * r)
        phi = np.arctan2(dy, dx)
        x = np.sin(theta) * np.cos(phi); y = np.sin(theta) * np.sin(phi); z = np.cos(theta)
        cr, sr = math.cos(math.radians(self.roll)), math.sin(math.radians(self.roll))
        xr = cr * x - sr * y; yr = sr * x + cr * y
        cp, sp = math.cos(math.radians(self.pitch)), math.sin(math.radians(self.pitch))
        E = xr; N = z * cp - yr * sp; U = z * sp + yr * cp
        az = (np.degrees(np.arctan2(E, N)) + self.yaw) % 360.0
        el = np.degrees(np.arctan2(U, np.hypot(E, N)))
        return az, el

    # ------------------------------------------------------------------ direction -> pixel
    def dir_to_pixel(self, az, el):
        """(azimuth deg, elevation deg) -> pixels. Inverse of pixel_to_dir (Newton on the radial term)."""
        az = np.radians(np.asarray(az, float) - self.yaw); el = np.radians(np.asarray(el, float))
        E = np.cos(el) * np.sin(az); N = np.cos(el) * np.cos(az); U = np.sin(el)
        cp, sp = math.cos(math.radians(self.pitch)), math.sin(math.radians(self.pitch))
        z = N * cp + U * sp; yr = -N * sp + U * cp; xr = E
        cr, sr = math.cos(math.radians(self.roll)), math.sin(math.radians(self.roll))
        x = cr * xr + sr * yr; y = -sr * xr + cr * yr
        theta = np.arccos(np.clip(z, -1, 1))
        phi = np.arctan2(y, x)
        r = theta.copy()
        for _ in range(8):                               # solve r (1 + k1 r^2) = theta
            f = r * (1 + self.k1 * r * r) - theta
            r = r - f / (1 + 3 * self.k1 * r * r)
        rad = r * self.focal
        u = self.width / 2 + rad * np.cos(phi); v = self.height / 2 - rad * np.sin(phi)
        return u, v

    def effective_hfov(self) -> float:
        """Real angular width across the image after distortion, degrees."""
        r = math.radians(self.hfov / 2)
        return 2 * math.degrees(r * (1 + self.k1 * r * r))
