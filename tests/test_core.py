import pytest
import numpy as np
from tests.testing_utils import DummyPhysicalSystem, DummyReferenceGenerator, DummyRewardFunction, DummyVisualization, \
    mock_instantiate, instantiate_dict
from gym.spaces import Tuple, Box
import gym_electric_motor
from gym_electric_motor.visualization import ConsolePrinter
from gym_electric_motor.core import ElectricMotorEnvironment, RewardFunction, \
    ReferenceGenerator, PhysicalSystem
import gym
import gym_electric_motor as gem


class TestElectricMotorEnvironment:
    test_class = ElectricMotorEnvironment
    key = ''

    @pytest.fixture
    def env(self):
        ps = DummyPhysicalSystem()
        rg = DummyReferenceGenerator()
        rf = DummyRewardFunction()
        vs = DummyVisualization()
        env = self.test_class(
            physical_system=ps,
            reference_generator=rg,
            reward_function=rf,
            visualization=vs
        )
        return env

    def test_make(self):
        if self.key != '':
            env = gem.make(self.key)
            assert type(env) == self.test_class

    @pytest.mark.parametrize(
        "physical_system, reference_generator, reward_function, state_filter, visualization, kwargs",
        [
            (DummyPhysicalSystem, DummyReferenceGenerator, DummyRewardFunction, None, None, {}),
            (
                    DummyPhysicalSystem(2), DummyReferenceGenerator, DummyRewardFunction(), ['dummy_state_0'],
                    ConsolePrinter, {'a': 1, 'b': 2}
            ),
            (
                    DummyPhysicalSystem(10), DummyReferenceGenerator(),
                    DummyRewardFunction(observed_states=['dummy_state_0']), ['dummy_state_0', 'dummy_state_2'], None, {}
            ),
        ]
    )
    def test_initialization(self, monkeypatch, physical_system, reference_generator, reward_function,
                            state_filter, visualization, kwargs):
        with monkeypatch.context() as m:
            instantiate_dict.clear()
            m.setattr(gym_electric_motor.core, "instantiate", mock_instantiate)
            env = gym_electric_motor.core.ElectricMotorEnvironment(
                physical_system=physical_system,
                reference_generator=reference_generator,
                reward_function=reward_function,
                visualization=visualization,
                state_filter=state_filter,
                **kwargs
            )

        # Assertions that the Keys are passed correctly to the instantiate fct
        assert physical_system == instantiate_dict[PhysicalSystem]['key']
        assert reference_generator == instantiate_dict[ReferenceGenerator]['key']
        assert reward_function == instantiate_dict[RewardFunction]['key']

        # Assertions that the modules that the instantiate functions returns are set correctly to the properties
        assert env.physical_system == instantiate_dict[PhysicalSystem]['instance']
        assert env.reference_generator == instantiate_dict[ReferenceGenerator]['instance']
        assert env.reward_function == instantiate_dict[RewardFunction]['instance']

        # Assertions for correct spaces
        assert env.action_space == instantiate_dict[PhysicalSystem]['instance'].action_space, 'Wrong action space'
        if state_filter is None:
            assert Tuple(
                (instantiate_dict[PhysicalSystem]['instance'].state_space,
                 instantiate_dict[ReferenceGenerator]['instance'].reference_space)) \
                   == env.observation_space, 'Wrong observation space'
        else:
            state_idxs = np.isin(physical_system.state_names, state_filter)
            state_space = Box(
                instantiate_dict[PhysicalSystem]['instance'].state_space.low[state_idxs],
                instantiate_dict[PhysicalSystem]['instance'].state_space.high[state_idxs],
            )
            assert Tuple(
                (state_space, instantiate_dict[ReferenceGenerator]['instance'].reference_space)
            ) == env.observation_space, 'Wrong observation space'
        assert env.reward_range == instantiate_dict[RewardFunction]['instance'].reward_range, 'Wrong reward range'

        # Test Correct passing of kwargs
        assert physical_system != DummyPhysicalSystem or env.physical_system.kwargs == kwargs
        assert reference_generator, DummyReferenceGenerator or env.reference_generator.kwargs == kwargs
        assert reward_function != DummyRewardFunction or env.reward_function.kwargs == kwargs
        assert visualization != DummyVisualization or env._visualization.kwargs == kwargs

    def test_reset(self, env):
        ps = env.physical_system
        rg = env.reference_generator
        rf = env.reward_function
        vs = env._visualization
        rf.last_state = rf.last_reference = ps.state = rg.get_reference_state = vs.reference_trajectory = None

        state, ref = env.reset()
        assert (state, ref) in env.observation_space, 'Returned values not in observation space'
        assert np.all(np.all(state == ps.state)), 'Returned state is not the physical systems state'
        assert np.all(ref == rg.reference_observation), 'Returned reference is not the reference generators reference'
        assert np.all(state == rg.get_reference_state), 'Incorrect state passed to the reference generator'
        assert np.all(vs.reference_trajectory == rg.trajectory), 'Incorrect trajectory passed to the visualization'
        assert rf.last_state == state, 'Incorrect state passed to the Reward Function'
        assert rf.last_reference == rg.reference_array, 'Incorrect Reference passed to the reward function'

    @pytest.mark.parametrize('action, set_done', [(0, False), (-1, False), (1, False), (2, True)])
    def test_step(self, env, action, set_done):
        ps = env.physical_system
        rg = env.reference_generator
        rf = env.reward_function

        rf.set_done(set_done)
        with pytest.raises(Exception):
            env.step(action), 'Environment goes through the step without previous reset'
        env.reset()
        (state, reference), reward, done, _ = env.step(action)
        assert np.all(state == ps.state[env.state_filter]), 'Returned state and Physical Systems state are not equal'
        assert rg.get_reference_state == ps.state,\
            'State passed to the Reference Generator not equal to Physical System state'
        assert rg.get_reference_obs_state == ps.state, \
            'State passed to the Reference Generator not equal to Physical System state'
        assert ps.action == action, 'Action passed to Physical System not equal to selected action'
        assert reward == -1 if set_done else 1
        assert done == set_done
        # If episode terminated, no further step without reset
        if set_done:
            with pytest.raises(Exception):
                env.step(action)

    def test_close(self, env):
        ps = env.physical_system
        rg = env.reference_generator
        rf = env.reward_function
        vs = env._visualization
        env.close()
        assert ps.closed, 'Physical System was not closed'
        assert rf.closed, 'Reward Function was not closed'
        assert rg.closed, 'Reference Generator was not closed'
        assert vs.closed, 'Visualization was not closed'

    @pytest.mark.parametrize("reference_generator", (DummyReferenceGenerator(),))
    def test_reference_generator_change(self, env, reference_generator):
        env.reset()
        env.reference_generator = reference_generator
        assert env.reference_generator == reference_generator, 'Reference Generator was not changed'
        # Without Reset an Exception has to be thrown
        with pytest.raises(Exception):
            env.step(env.action_space.sample()), 'After Reference Generator change was no reset required'
        env.reset()
        # No Exception raised
        env.step(env.action_space.sample())

    @pytest.mark.parametrize("reward_function", (DummyRewardFunction(),))
    def test_reward_function_change(self, env, reward_function):
        env.reset()
        reward_function.set_modules(physical_system=env.physical_system, reference_generator=env.reference_generator)
        env.reward_function = reward_function
        assert env.reward_function == reward_function, 'Reward Function was not changed'
        # Without Reset an Exception has to be thrown
        with pytest.raises(Exception):
            env.step(env.action_space.sample()), 'After Reward Function change was no reset required'
        env.reset()
        # No Exception raised
        env.step(env.action_space.sample())

    @pytest.mark.parametrize("number_states, state_filter, expected_result",
                             ((1, ['dummy_state_0'], [10]),
                              (3, ['dummy_state_0', 'dummy_state_1', 'dummy_state_2'], [10, 20, 30]),
                              (3, ['dummy_state_1'], [20])))
    def test_limits(self, number_states, state_filter, expected_result):
        ps = DummyPhysicalSystem(state_length=number_states)
        rg = DummyReferenceGenerator()
        rf = DummyRewardFunction()
        vs = DummyVisualization()
        env = self.test_class(
            physical_system=ps,
            reference_generator=rg,
            reward_function=rf,
            visualization=vs,
            state_filter=state_filter
        )
        assert all(env.limits == expected_result)


class TestRewardFunction:

    @staticmethod
    def mock_standard_reward(*_):
        return 1

    @staticmethod
    def mock_limit_violation_reward(*_):
        return -1

    @staticmethod
    def mock_reward_function(*_):
        return 'Reward Function called'

    @pytest.mark.parametrize("observed_states", (['dummy_state_0'], ['dummy_state_0', 'dummy_state_1']))
    def test_initialization(self, observed_states):
        RewardFunction(observed_states)

    @pytest.mark.parametrize("reward_function, physical_system, reference_generator, expected_observed_states", (
            (RewardFunction('dummy_state_0'), DummyPhysicalSystem(), DummyReferenceGenerator(), ['dummy_state_0']),
            (RewardFunction(['dummy_state_0', 'dummy_state_2']), DummyPhysicalSystem(3), DummyReferenceGenerator(),
             ['dummy_state_0', 'dummy_state_2']),
            (RewardFunction('all'), DummyPhysicalSystem(3), DummyReferenceGenerator(),
             ['dummy_state_0', 'dummy_state_1', 'dummy_state_2']),
            (RewardFunction('currents'), DummyPhysicalSystem(3, 'i'), DummyReferenceGenerator(),
             ['i_0', 'i_1', 'i_2']),
            (RewardFunction(['voltages']), DummyPhysicalSystem(3, 'u'), DummyReferenceGenerator(),
             ['u_0', 'u_1', 'u_2'])
        )
    )
    def test_set_modules(self, monkeypatch, reward_function, physical_system, reference_generator,
                         expected_observed_states):
        reward_function.set_modules(physical_system, reference_generator)
        assert np.all(
            reward_function._observed_states == np.isin(physical_system.state_names, expected_observed_states))

    @pytest.mark.parametrize("reward_function, physical_system, reference_generator, expected_observed_states", (
            (RewardFunction(['currents', 'voltages']), DummyPhysicalSystem(5), DummyReferenceGenerator(),
             ['i_a', 'i_e', 'u_a']),
            (RewardFunction(['currents', 'omega']), DummyPhysicalSystem(5), DummyReferenceGenerator(),
             ['omega', 'i_a', 'i_e']),
            (RewardFunction(['omega', 'voltages']), DummyPhysicalSystem(5), DummyReferenceGenerator(),
             ['omega', 'u_a']),
            (RewardFunction(['currents', 'omega', 'voltages']), DummyPhysicalSystem(5), DummyReferenceGenerator(),
             ['omega', 'i_a', 'i_e', 'u_a']),
    ))
    def test_set_modules_combined_observed_states(self, monkeypatch, reward_function, physical_system,
                                                  reference_generator, expected_observed_states):
        physical_states = ['i_a', 'i_e', 'u_a', 'omega', 'torque']
        physical_system._state_names = physical_states
        reward_function.set_modules(physical_system, reference_generator)
        assert np.all(
            reward_function._observed_states == np.isin(physical_system.state_names, expected_observed_states))

    @pytest.mark.parametrize(
        "physical_system, reference_generator", ((DummyPhysicalSystem(3), DummyReferenceGenerator()),)
    )
    @pytest.mark.parametrize("observed_state_idx, violated_state_idx", (
            ([0, 1], [2]),
            ([0, 1, 2], []),
            ([2], [1, 2])
    ))
    def test_reward(self, monkeypatch, physical_system, reference_generator, observed_state_idx, violated_state_idx):
        observed_states = list(np.array(physical_system.state_names)[observed_state_idx])
        rf = RewardFunction(observed_states)
        rf.set_modules(physical_system, reference_generator)
        monkeypatch.setattr(rf, "_reward", self.mock_standard_reward)
        monkeypatch.setattr(rf, "_limit_violation_reward", self.mock_limit_violation_reward)
        state = np.ones_like(physical_system.state_names, dtype=float) * 0.5
        state[violated_state_idx] = 1.5
        reward, done = rf.reward(state, None)
        if np.any(np.isin(observed_state_idx, violated_state_idx)):
            assert reward == -1
            assert done
        else:
            assert reward == 1
            assert not done
        # Test negative limit violations
        state[violated_state_idx] = -1.5
        reward, done = rf.reward(state, None)

        if np.any(np.isin(observed_state_idx, violated_state_idx)):
            assert reward == -1
            assert done
        else:
            assert reward == 1
            assert not done

    def test_call(self, monkeypatch):
        rf = RewardFunction()
        monkeypatch.setattr(rf, "reward", self.mock_reward_function)
        result = rf(1, 2)
        assert result == 'Reward Function called'


class TestReferenceGenerator:
    test_object = None
    initial_state = np.array([1, 2, 3, 4, 5]) / 5
    _reference = 0.5
    _observation = np.zeros(5)
    counter_obs = 0

    def mock_get_reference_observation(self, initial_state):
        assert all(initial_state == self.initial_state)
        self.counter_obs += 1
        return self._observation

    def mock_get_reference(self, initial_state):
        assert all(initial_state == self.initial_state)
        return self._reference

    def test_reference_generator_reset(self, monkeypatch):
        monkeypatch.setattr(ReferenceGenerator, "get_reference_observation", self.mock_get_reference_observation)
        monkeypatch.setattr(ReferenceGenerator, "get_reference", self.mock_get_reference)
        test_object = ReferenceGenerator()
        reference, observation, kwargs = test_object.reset(self.initial_state)
        assert reference == self._reference
        assert all(observation == self._observation)
        assert kwargs is None


class TestPhysicalSystem:

    def test_initialization(self):
        action_space = gym.spaces.Discrete(3)
        state_space = gym.spaces.Box(-1, 1, shape=(3,))
        state_names = [f'dummy_state_{i}' for i in range(3)]
        tau = 1
        ps = PhysicalSystem(action_space, state_space, state_names, tau)
        assert ps.action_space == action_space
        assert ps.state_space == state_space
        assert ps.state_names == state_names
        assert ps.tau == tau
        assert ps.k == 0
