import numpy as np
from enum import Enum
from typing import Tuple, Union

from flygym.examples.locomotion import HybridTurningController


class WalkingState(Enum):
    FORWARD = 0
    TURN_LEFT = 1
    TURN_RIGHT = 2
    STOP = 3


class RandomExplorationController:
    def __init__(
        self,
        dt: float,
        forward_dn_drive: Tuple[float, float] = (1.0, 1.0),
        left_turn_dn_drive: Tuple[float, float] = (-0.4, 1.2),
        right_turn_dn_drive: Tuple[float, float] = (1.2, -0.4),
        turn_duration_mean: float = 0.4,
        turn_duration_std: float = 0.1,
        lambda_turn: float = 1.0,
        seed: int = 0,
        init_time: float = 0.1,
    ) -> None:
        self.random_state = np.random.RandomState(seed)
        self.dt = dt
        self.init_time = init_time
        self.curr_time = 0.0
        self.curr_state: WalkingState = WalkingState.FORWARD
        self._curr_turn_duration: Union[None, float] = None

        # DN drives
        self.dn_drives = {
            WalkingState.FORWARD: np.array(forward_dn_drive),
            WalkingState.TURN_LEFT: np.array(left_turn_dn_drive),
            WalkingState.TURN_RIGHT: np.array(right_turn_dn_drive),
        }

        # Turning related parameters
        self.turn_duration_mean = turn_duration_mean
        self.turn_duration_std = turn_duration_std
        self.lambda_turn = lambda_turn

    def step(self):
        # Upon spawning, just walk straight for a bit (init_time) for things to settle
        if self.curr_time < self.init_time:
            self.curr_time += self.dt
            return WalkingState.FORWARD, self.dn_drives[WalkingState.FORWARD]

        # Forward -> turn transition
        if self.curr_state == WalkingState.FORWARD:
            p_nochange = np.exp(-self.lambda_turn * self.dt)
            if self.random_state.rand() > p_nochange:
                # decide turn duration and direction
                self._curr_turn_duration = self.random_state.normal(
                    self.turn_duration_mean, self.turn_duration_std
                )
                self.curr_state = self.random_state.choice(
                    [WalkingState.TURN_LEFT, WalkingState.TURN_RIGHT]
                )
                self.curr_state_start_time = self.curr_time

        # Turn -> forward transition
        if self.curr_state in (WalkingState.TURN_LEFT, WalkingState.TURN_RIGHT):
            if self.curr_time - self.curr_state_start_time > self._curr_turn_duration:
                self.curr_state = WalkingState.FORWARD
                self.curr_state_start_time = self.curr_time

        self.curr_time += self.dt
        return self.curr_state, self.dn_drives[self.curr_state]


class PathIntegrationNMF(HybridTurningController):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._last_end_effector_pos: Union[None, np.ndarray] = None
        self.total_stride_lengths_hist = []
        self.heading_estimate_hist = []
        self.pos_estimate_hist = []

    def step(self, action):
        obs, reward, terminated, truncated, info = super().step(action)

        # Update camera position
        self.arena.update_cam_pos(self.physics, obs["fly"][0, :2])

        # Calculate stride since last step for each leg
        ee_pos_rel = self.absolute_to_relative_pos(
            obs["end_effectors"][:, :2], obs["fly"][0, :2], obs["fly_orientation"][:2]
        )
        if self._last_end_effector_pos is None:
            ee_diff = np.zeros_like(ee_pos_rel)
        else:
            ee_diff = ee_pos_rel - self._last_end_effector_pos
        self._last_end_effector_pos = ee_pos_rel
        obs["stride_diff_unmasked"] = ee_diff

        return obs, reward, terminated, truncated, info

    @staticmethod
    def absolute_to_relative_pos(
        pos: np.ndarray, base_pos: np.ndarray, heading: np.ndarray
    ) -> np.ndarray:
        rel_pos = pos - base_pos
        heading = heading / np.linalg.norm(heading)
        angle = np.arctan2(heading[1], heading[0])
        rot_matrix = np.array(
            [[np.cos(-angle), -np.sin(-angle)], [np.sin(-angle), np.cos(-angle)]]
        )
        pos_rotated = np.dot(rel_pos, rot_matrix.T)
        return pos_rotated
