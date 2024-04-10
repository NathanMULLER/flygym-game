from flygym.arena import BaseArena
from flygym import Fly
import numpy as np
from typing import Tuple, Optional


class MovingFlyArena(BaseArena):
    """Flat terrain with a hovering moving fly.

    Attributes
    ----------
    arena : mjcf.RootElement
        The arena object that the terrain is built on.
    fly_pos : Tuple[float,float,float]
        The position of the floating fly in the arena.

    Parameters
    ----------
    size : Tuple[int, int]
        The size of the terrain in (x, y) dimensions.
    friction : Tuple[float, float, float]
        Sliding, torsional, and rolling friction coefficients, by default
        (1, 0.005, 0.0001)
    obj_radius : float
        Radius of the spherical floating fly in mm.
    init_fly_pos : Tuple[float,float]
        Initial position of the fly, by default (5, 0).
    move_speed : float
        Speed of the moving fly. By default 10.
    move_direction : str
        Which way the fly moves toward first. Can be "left", "right", or
        "random". By default "right".
    lateral_magnitude : float
        Magnitude of the lateral movement of the fly as a multiplier of
        forward velocity. For example, when ``lateral_magnitude`` is 1, the
        fly moves at a heading (1, 1) when its movement is the most
        lateral. By default 2.
    """

    def __init__(
        self,
        terrain: str = "flat",
        x_range: Optional[Tuple[float, float]] = (-10, 25),
        y_range: Optional[Tuple[float, float]] = (-20, 20),
        block_size: Optional[float] = 1.3,
        height_range: Optional[Tuple[float, float]] = (0.2, 0.2),
        rand_seed: int = 0,
        ground_alpha: float = 1,
        friction=(1, 0.005, 0.0001),
        obj_radius=1,
        init_fly_pos=(5, 0),
        move_speed=10,
        move_direction="right",
        lateral_magnitude=2,
    ):
        super().__init__()
        self.terrain = terrain
        self.init_fly_pos = (*init_fly_pos, obj_radius)
        self.fly_pos = np.array(self.init_fly_pos, dtype="float32")
        self.friction = friction
        self.move_speed = move_speed
        self.curr_time = 0
        self.move_direction = move_direction
        self.lateral_magnitude = lateral_magnitude
        if move_direction == "left":
            self.y_mult = 1
        elif move_direction == "right":
            self.y_mult = -1
        elif move_direction == "random":
            self.y_mult = np.random.choice([-1, 1])
        else:
            raise ValueError("Invalid move_direction")

        # Add ground
        if terrain == "flat":
            ground_size = [300, 300, 1]
            chequered = self.root_element.asset.add(
                "texture",
                type="2d",
                builtin="checker",
                width=300,
                height=300,
                rgb1=(0.8, 0.8, 0.8),
                rgb2=(0.9, 0.9, 0.9),
            )
            grid = self.root_element.asset.add(
                "material",
                name="grid",
                texture=chequered,
                texrepeat=(60, 60),
                reflectance=0.1,
            )
            self.root_element.worldbody.add(
                "geom",
                type="plane",
                name="ground",
                material=grid,
                size=ground_size,
                friction=friction,
            )
        elif terrain == "blocks":
            self.x_range = x_range
            self.y_range = y_range
            self.block_size = block_size
            self.height_range = height_range
            rand_state = np.random.RandomState(rand_seed)

            x_centers = np.arange(x_range[0] + block_size / 2, x_range[1], block_size)
            y_centers = np.arange(y_range[0] + block_size / 2, y_range[1], block_size)
            for i, x_pos in enumerate(x_centers):
                for j, y_pos in enumerate(y_centers):
                    is_i_odd = i % 2 == 1
                    is_j_odd = j % 2 == 1

                    if is_i_odd != is_j_odd:
                        height = 0.1
                    else:
                        height = 0.1 + rand_state.uniform(*height_range)

                    self.root_element.worldbody.add(
                        "geom",
                        type="box",
                        size=(
                            block_size / 2 + 0.1 * block_size / 2,
                            block_size / 2 + 0.1 * block_size / 2,
                            height / 2 + block_size / 2,
                        ),
                        pos=(
                            x_pos,
                            y_pos,
                            height / 2 - block_size / 2,
                        ),
                        rgba=(0.3, 0.3, 0.3, ground_alpha),
                        friction=friction,
                    )

            self.root_element.worldbody.add("body", name="base_plane")
        else:
            raise ValueError(f"Invalid terrain '{terrain}'")

        # Add fly
        self._prev_pos = complex(*self.init_fly_pos[:2])

        fly = Fly().model
        fly.model = "Animat_2"

        for light in fly.find_all(namespace="light"):
            light.remove()

        spawn_site = self.root_element.worldbody.add(
            "site",
            pos=self.fly_pos,
            euler=(0, 0, 0),
        )
        self.freejoint = spawn_site.attach(fly).add("freejoint")

        # Add camera
        self.birdeye_cam = self.root_element.worldbody.add(
            "camera",
            name="birdeye_cam",
            mode="fixed",
            pos=(15, 0, 35),
            euler=(0, 0, 0),
            fovy=45,
        )
        self.birdeye_cam_zoom = self.root_element.worldbody.add(
            "camera",
            name="birdeye_cam_zoom",
            mode="fixed",
            pos=(15, 0, 20),
            euler=(0, 0, 0),
            fovy=45,
        )

    def get_spawn_position(self, rel_pos, rel_angle):
        return rel_pos, rel_angle

    def step(self, dt, physics):
        heading_vec = np.array(
            [1, self.lateral_magnitude * np.cos(self.curr_time * 3) * self.y_mult]
        )
        heading_vec /= np.linalg.norm(heading_vec)
        self.fly_pos[:2] += self.move_speed * heading_vec * dt

        curr_pos = complex(*self.fly_pos[:2])
        q = np.exp(1j * np.angle(curr_pos - self._prev_pos) / 2)
        qpos = (*self.fly_pos, q.real, 0, 0, q.imag)
        physics.bind(self.freejoint).qpos = qpos
        self._prev_pos = curr_pos

        self.curr_time += dt

    def reset(self, physics):
        self._prev_pos = complex(*self.init_fly_pos[:2])

        if self.move_direction == "random":
            self.y_mult = np.random.choice([-1, 1])
        self.curr_time = 0
        self.fly_pos = np.array(self.init_fly_pos, dtype="float32")
        physics.bind(self.object_body).mocap_pos = self.fly_pos
