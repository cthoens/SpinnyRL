import asyncio
import numpy as np
from SpinnyEnv import SpinnyEnv
from Models.KerasModel import KerasModel
from Methods.TemporalDifference import Sarsa
from Policies import EpsilonGreedyPolicy, GreedyPolicy
from Utilities.Eval import MetricsLogger, validate_policy
from KerasModelBuilders import conv1_model, conv2_model


class ValidationMetrics:
    def __init__(self):
        self.training_avg_reward = 0.0
        self.training_avg_rms = 0.0
        self.validation_avg_reward = 0.0


async def run():
    np.random.seed(643674)
    env = SpinnyEnv()
    future = asyncio.ensure_future(env.interface.run())
    print(env.observation_space.shape)
    model = KerasModel(env, conv2_model(env))
    training_policy = EpsilonGreedyPolicy(model, 0.1)
    mc = Sarsa(env, model, training_policy)

    await asyncio.sleep(0)

    training_policy.exploration = 0.1
    env.max_steps = 35
    mc.alpha = 0.01
    model.epochs = 100
    validation_episode_count = 200

    try:
        episode_count = 50001
        for i in range(episode_count):
            await mc.run_episode()

    except KeyboardInterrupt:
        print("Keyborad interrupt")

    await env.close()
    await future

asyncio.get_event_loop().run_until_complete(run())
