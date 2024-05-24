#!/usr/bin/env python
# python standard libraries
import os
from pathlib import Path
import sys
import socket
from onpolicy.utils.plot3d_test import plot_track, plot_git, get_track_gif
from onpolicy.algorithms.NeuPL.mixing_policy import Parallel_mixing_policy as Multi_mix_policy

# third-party packages
import numpy as np
import setproctitle
import torch
import wandb
import copy

# code repository sub-packages
from onpolicy.config import get_config
from onpolicy.envs.uav.UAV_env import UAVEnv
from onpolicy.algorithms.NeuPL.train_NeuPL_WF import find_unique_rows, compact_dictionaries, restore_eval_policy
from onpolicy.algorithms.NeuPL.Policy_prob_matrix import Nash_matrix as graph_solver
from onpolicy.algorithms.r_mappo.algorithm.rMAPPOPolicy_sigma import R_MAPPOPolicy as Policy_module
# from onpolicy.algorithms.policy_DG.simple_policy_rule import Policy_E2P_3Doptimal as Evader_rule_policy
# from onpolicy.algorithms.policy_DG.simple_policy_rule import Policy_P2E_straight as Pursuer_rule_policy
from onpolicy.algorithms.policy_DG.simple_policy_rule import Policy_P2E_straight as Pursuer_rule_policy
from onpolicy.algorithms.policy_DG.simple_policy_rule import Policy_E2L_straight as Evader_rule_policy
from onpolicy.algorithms.NeuPL.eval_match import eval_match_uav as evaluator

def make_train_env(all_args):
    def get_env_fn(rank):
        def init_env():
            if all_args.env_name == "UAV":
                ## TODO: pass hyper-parameters to the environment
                env = UAVEnv(all_args)
            else:
                print("Can not support the " +
                      all_args.env_name + " environment.")
                raise NotImplementedError
            env.seed(all_args.seed + rank * 1000)
            return env
        return init_env()
    return get_env_fn(0)


def make_eval_env(all_args):
    def get_env_fn(rank):
        def init_env():
            if all_args.env_name == "UAV":
                ## TODO: pass hyper-parameters to the environment
                env = UAVEnv(all_args)
            else:
                print("Can not support the " +
                      all_args.env_name + " environment.")
                raise NotImplementedError
            env.seed(all_args.seed * 50000 + rank * 10000)
            return env
        return init_env()
    return get_env_fn(0)

# def restore_eval_policy(policy, model_dir, label_str, use_mixer = True):
#     """Restore policy's networks from a saved model."""
#     policy_actor_state_dict = torch.load(str(model_dir) + '/actor_' + label_str + '.pt')
#     policy.actor.load_state_dict(policy_actor_state_dict)
#     if use_mixer:
#         policy_mixer_state_dict = torch.load(str(model_dir) + '/mixer_' + label_str + '.pt')
#         policy.mixer.load_state_dict(policy_mixer_state_dict)

def creat_empty_policy(args, envs, device):
    empty_policy = Policy_module(args,
                        envs.world.obs_space[0],
                        envs.world.obs_space[0],
                        envs.world.act_space[0],
                        device)
    return empty_policy

def parse_args(args, parser):
    parser.add_argument("--scenario_name", type=str,
                        default="simple_uav", 
                        help="which scenario to run on.")
    parser.add_argument("--num_agents", type=int, default=3,
                        help="number of controlled players.")
    parser.add_argument("--eval_deterministic", action="store_false", 
                        default=True, 
                        help="by default True. If False, sample action according to probability")
    parser.add_argument("--share_reward", action='store_false', 
                        default=True, 
                        help="by default true. If false, use different reward for each agent.")

    parser.add_argument("--save_videos", action="store_true", default=False, 
                        help="by default, do not save render video. If set, save video.")
    parser.add_argument("--video_dir", type=str, default="", 
                        help="directory to save videos.")
    parser.add_argument("--file_path", type=str, default="")
    
    #added by junyu
    parser.add_argument("--encoder_layer_N",type=int,
                        default=1, help="number of encoder layers")
    parser.add_argument("--encoder_hidden_size", type=int,
                        default=16, help="hidden size of encoder")
    parser.add_argument("--proprio_shape", type=int, default=13,
                        help="proprio_shape")
    parser.add_argument("--teammate_shape", type=int, default=7,
                        help="teammate")
    parser.add_argument("--opponent_shape", type=int, default=3,
                        help="opponent_shape")
    parser.add_argument("--n_head", type=int, default=4, help="n_head")
    parser.add_argument("--d_k", type=int, default= 16, help="d_k")
    parser.add_argument("--attn_size", type=int, default=16, help="attn_size")

    parser.add_argument("--team_name", type=str, default="evader")
    parser.add_argument("--oppo_name", type=str, default="pursuer")
    parser.add_argument("--sigma_layer_N",type=int, default=1)

    # NeuPL setting
    parser.add_argument("--population_size", type=int, default=5)
    parser.add_argument("--runner_num", type=int, default=1)
    parser.add_argument("--global_steps", type=int, default=0)
    parser.add_argument("--eval_episode_num", type=int, default=10)
    parser.add_argument("--total_round", type=int, default=10)
    parser.add_argument("--channel_interval", type=int, default=10)
    parser.add_argument("--use_mix_policy", action='store_true', default=False)
    parser.add_argument("--use_inherit_policy", action='store_false', default=True)
    parser.add_argument("--use_warmup", action='store_false', default=True)
    parser.add_argument("--single_round", action='store_true', default=False)
    parser.add_argument("--policy_backup_dir", type=str, default=None)
    parser.add_argument("--begin_inx", type=int, default=1)
    parser.add_argument("--role_number", type=int, default=0)
    parser.add_argument("--use_share_policy", action='store_false', default=True)

    parser.add_argument("--use_track_recorder", action='store_true', default=False)
    parser.add_argument("--use_payoff_eval", action='store_true', default=False)
    parser.add_argument("--track_n", type=int, default=1)
    parser.add_argument("--population_type", type=str, default="neupl")
    parser.add_argument("--num_policy_p1", type=int, default=100)
    parser.add_argument("--num_policy_p2", type=int, default=100)
    parser.add_argument("--PT_pursuer", type=str, default=None)
    parser.add_argument("--PT_evader", type=str, default=None)
    parser.add_argument("--dir_pursuer", type=str, default=None)
    parser.add_argument("--dir_evader", type=str, default=None)
    
    all_args = parser.parse_known_args(args)[0]

    return all_args


def main(args):
    parser = get_config()
    all_args = parse_args(args, parser)
    if all_args.algorithm_name == "rmappo":
        print("u are choosing to use rmappo, we set use_recurrent_policy to be True")
        all_args.use_recurrent_policy = True
        all_args.use_naive_recurrent_policy = False
    elif all_args.algorithm_name == "mappo":
        print("u are choosing to use mappo, we set use_recurrent_policy & use_naive_recurrent_policy to be False")
        all_args.use_recurrent_policy = False 
        all_args.use_naive_recurrent_policy = False
    elif all_args.algorithm_name == "ippo":
        print("u are choosing to use ippo, we set use_centralized_V to be False. Note that GRF is a fully observed game, so ippo is rmappo.")
        all_args.use_centralized_V = False
    else:
        raise NotImplementedError

    # cuda
    if all_args.cuda and torch.cuda.is_available():
        print("choose to use gpu...")
        device = torch.device("cuda")
        # torch.set_num_threads(all_args.n_training_threads)
        if all_args.cuda_deterministic:
            torch.backends.cudnn.benchmark = False
            torch.backends.cudnn.deterministic = True
    else:
        print("choose to use cpu...")
        device = torch.device("cpu")
        # torch.set_num_threads(all_args.n_training_threads)

    # run dir
    run_dir = Path(os.path.split(os.path.dirname(os.path.abspath(__file__)))[
                   0] + "/results") / all_args.env_name / all_args.scenario_name / all_args.algorithm_name / all_args.experiment_name
    if not run_dir.exists():
        os.makedirs(str(run_dir))

    # wandb
    if all_args.use_wandb:
        run = wandb.init(config=all_args,
                         project=all_args.env_name,
                        #  entity=all_args.user_name,
                         notes=socket.gethostname(),
                         name="-".join([
                            all_args.algorithm_name,
                            all_args.experiment_name,
                            "seed" + str(all_args.seed)
                         ]),
                         group=all_args.scenario_name,
                        #  dir=str(run_dir),
                         job_type="training",
                         reinit=False)
    else:
        if not run_dir.exists():
            curr_run = 'run1'
        else:
            exst_run_nums = [int(str(folder.name).split('run')[1]) for folder in run_dir.iterdir() if str(folder.name).startswith('run')]
            if len(exst_run_nums) == 0:
                curr_run = 'run1'
            else:
                curr_run = 'run%i' % (max(exst_run_nums) + 1)
        run_dir = run_dir / curr_run
        if not run_dir.exists():
            os.makedirs(str(run_dir))
    
    print("run_dir=",run_dir)

    setproctitle.setproctitle("-".join([
        all_args.env_name, 
        all_args.scenario_name, 
        all_args.algorithm_name, 
        all_args.experiment_name
    ]) + "@" + all_args.user_name)
    
    # seed
    torch.manual_seed(all_args.seed)
    torch.cuda.manual_seed_all(all_args.seed)
    np.random.seed(all_args.seed)

    # run experiments
    if all_args.share_policy:
        from onpolicy.runner.shared.uav_dual_runner import UAV_Dual_Runner as Runner
    else:
        from onpolicy.runner.separated.uav_dual_runner import UAV_Dual_Runner as Runner
    
    if all_args.dir_evader is None or all_args.PT_evader is None:
        all_args.dir_evader = all_args.dir_pursuer
        all_args.PT_evader = all_args.PT_pursuer

    probs_p1 = np.load(os.path.join(all_args.dir_evader, 'probs_p1.npy'))
    probs_p2 = np.load(os.path.join(all_args.dir_pursuer, 'probs_p2.npy'))
    policy_num_p1 = min(all_args.population_size, all_args.num_policy_p1)
    policy_num_p2 = min(all_args.population_size, all_args.num_policy_p2)
    effect_p1_probs, effect_p1_map = find_unique_rows(matrix=probs_p1, max_num=policy_num_p2)
    effect_p2_probs, effect_p2_map = find_unique_rows(matrix=probs_p2, max_num=policy_num_p1)

    effect_p1_ids, effect_p2_ids = effect_p2_probs, effect_p1_probs
    effect_p2_id_map, effect_p1_id_map = compact_dictionaries(effect_p1_map, effect_p2_map)
    policy_num_p1 = min(effect_p1_ids.shape[0] + 1, all_args.num_policy_p1)
    policy_num_p2 = min(effect_p2_ids.shape[0] + 1 , all_args.num_policy_p2)

    # env init
    all_args.team_name = 'pursuer'
    all_args.oppo_name = 'evader'

    envs = make_train_env(all_args)
    #eval_envs = make_eval_env(all_args) if all_args.use_eval else None
    eval_envs = make_eval_env(all_args)
    num_agents = all_args.num_agents
    all_args.episode_length = envs.episode_length

    # all_args.proprio_shape, all_args.teammate_shape, all_args.opponent_shape =  envs.world.sub_role_shape[all_args.team_name]['proprio_shape'], \
    #                                                                             envs.world.sub_role_shape[all_args.team_name]['teammate_shape'], \
    #                                                                             envs.world.sub_role_shape[all_args.team_name]['opponent_shape']
    
    # print("{} : p_shape {}, t_shape {}, o_shape {}.".format(all_args.team_name, all_args.proprio_shape, all_args.teammate_shape, all_args.opponent_shape))

    oppo_policies = []

    #pre_load_dir = "/home/qiyuan/workspace/flightmare_pe/flightrl/on-policy/onpolicy/scripts/train_uav_scripts/wandb/run-20231116_143151-3hiik73i/files"
    pre_load_dir = "/home/qiyuan/workspace/flightmare_pe/flightrl/on-policy/onpolicy/scripts/train_uav_scripts/wandb/run-20231204_150636-zi3n9hd8/files"

    if all_args.PT_pursuer == "neupl":
        discrete_policy = False
    elif all_args.PT_pursuer == "frozen_policy":
        discrete_policy = True
    else:
        raise NotImplementedError
    
    #empty_policy = creat_oppo_policy(all_args, eval_envs, pre_load_dir, str(eval_envs.world.oppo_name) + str(2), device)
    pursuer_policy_list = []
    for i in range(policy_num_p1):
        empty_policy = Policy_module(all_args,
                            envs.world.observation_space[0],
                            envs.world.observation_space[0],
                            envs.world.action_space[0],
                            device)
        if i==0:
            pos_e = eval_envs.world.num_team * 3
            pursuer_policy_list.append(Pursuer_rule_policy(empty_policy, max_vel=5, pos_e_inx=pos_e, device=device))
        else:
            if discrete_policy:
                restore_eval_policy(empty_policy, all_args.dir_pursuer, 'pursuer', use_mixer = empty_policy.use_mixer, head_str=("frozen_policy_" + str(i)))
            else:
                restore_eval_policy(empty_policy, all_args.dir_pursuer, 'pursuer', use_mixer = empty_policy.use_mixer)
            p2_sigma = torch.from_numpy(effect_p1_ids[i-1])
            # set sigma of player2's j-th policy
            empty_policy.set_sigma(np.tile(p2_sigma,(1,1)))
            empty_policy.set_fusion_false()
            pursuer_policy_list.append(empty_policy)




    # mat_path = "/home/qiyuan/workspace/flightmare_pe/flightrl/on-policy/onpolicy/algorithms/NeuPL/dataforattackerV2.mat"
    # grid = (np.linspace(10, 210, 101), np.linspace(-100, 100, 101), np.linspace(-100, 100, 101))
    mat_path = '/home/qiyuan/workspace/flightmare_pe/flightrl/on-policy/onpolicy/algorithms/NeuPL/dataforattackerV3.mat'
    grid = (np.linspace(25, 205, 46), np.linspace(-100, 100, 51), np.linspace(0, 100, 26),
            np.linspace(-5, 205, 36), np.linspace(-5, 205, 36))
    # mat_path = '/home/qiyuan/workspace/flightmare_pe/flightrl/on-policy/onpolicy/algorithms/NeuPL/dataforattackerV4.mat'
    # grid1V1 = (np.linspace(20, 200, 46), np.linspace(-5, 205, 36),
    #        np.linspace(-120, 120, 41), np.linspace(-120, 120, 41), np.linspace(-120, 120, 41))
    # grid2V1 = (np.linspace(20, 200, 19), np.linspace(-5, 205, 15),
    #         np.linspace(-24, 24, 9), np.linspace(-24, 24, 9), np.linspace(-24, 24, 9),
    #         np.linspace(-24, 24, 9), np.linspace(-24, 24, 9), np.linspace(-24, 24, 9))
    # grid = (grid1V1, grid2V1)
    # mat_path = "/home/qiyuan/workspace/flightmare_pe/flightrl/on-policy/onpolicy/algorithms/NeuPL/dataforattacker.mat"
    # samples = np.linspace(-105, 105, 51)

    pos_p_in = all_args.proprio_shape
    print("pos_p_inx = ", pos_p_in)

    if all_args.PT_evader == "neupl":
        discrete_policy = False
    elif all_args.PT_evader == "frozen_policy":
        discrete_policy = True
    else:
        raise NotImplementedError
    
    evader_policy_list = []
    for i in range(policy_num_p2):
        empty_policy = Policy_module(all_args,
                            envs.world.oppo_obs_space[0],
                            envs.world.oppo_obs_space[0],
                            envs.world.oppo_act_space[0],
                            device)
        if i==0:
            evader_policy_list.append(Evader_rule_policy(copy.deepcopy(empty_policy), max_vel=7, device=device))
        else:
            if discrete_policy:
                restore_eval_policy(empty_policy, all_args.dir_evader, 'evader', use_mixer = empty_policy.use_mixer, head_str=("frozen_policy_" + str(i)))
            else:
                restore_eval_policy(empty_policy, all_args.dir_evader, 'evader', use_mixer = empty_policy.use_mixer)
            p1_sigma = torch.from_numpy(effect_p2_ids[i-1])
            # set sigma of player2's j-th policy
            empty_policy.set_sigma(np.tile(p1_sigma,(1,1)))
            empty_policy.set_fusion_false()
            evader_policy_list.append(empty_policy)

    # eval_envs.world.oppo_policy = Evader_rule_policy(empty_policy, max_vel=7, mat_path=mat_path, grid=grid, device = device)
    # eval_envs.world.oppo_policy = Evader_rule_policy(empty_policy, max_vel=7, device=device)

    # for i in range(6):
    #     oppo_policies.append(creat_oppo_policy(all_args, eval_envs, pre_load_dir, str(eval_envs.world.oppo_name) + str(i+1), device))

    # oppo_probs = np.array([1, 1, 1, 1, 1, 1], dtype=float)

    # eval_envs.world.oppo_policy = Multi_mix_policy(all_args.n_rollout_threads, oppo_policies, probs= oppo_probs)
    
    #eval_envs.world.oppo_policy = creat_oppo_policy(all_args, eval_envs, pre_load_dir, str(eval_envs.world.oppo_name) + str(all_args.evader_num), device)

    # num_agents = eval_envs.world.num_team
    # all_args.num_agents = num_agents
    
    all_args.episode_length = envs.episode_length

    eval = evaluator(pursuer_policy_list, evader_policy_list, eval_envs)

    eval.get_win_prob_mat(all_args.n_rollout_threads, all_args.eval_episode_num)

    payoff_mat = (eval.win_num_mat - eval.lose_num_mat)/(all_args.n_rollout_threads * all_args.eval_episode_num)

    print("payoff_mat = ", payoff_mat)

    p1_space = ["pursuer_" + str(i) for i in range(policy_num_p1)]
    p2_space = ["evader_" + str(i) for i in range(policy_num_p2)]

    solver = graph_solver(p1_space, p2_space)
    solver.update_prob_matrix(payoff_mat, effect_p1_id_map, effect_p2_id_map)

    print("payoff_line_p1 = ", solver.p1_payoff_line)
    print("exploitability = ", solver.exploitability_avg)
    print("exploitability_p1 = ", solver.exploitability_p1)
    print("exploitablilty_p2 = ", solver.exploitability_p2)

    # all_args.use_mixer = True if num_agents >= 2 else False

    # if all_args.use_track_recorder:
    #     for kk in range(all_args.track_n):
    #         print("round {}/{}".format(kk, all_args.track_n))
    #         obs_array, info_array = eval.get_track_array()
    #         for i in range(policy_num_p1):
    #             for j in range(policy_num_p2):
    #                 track_length = len(obs_array[i][j])
    #                 pursuer_track = np.zeros((track_length, eval_envs.world.num_team,3))
    #                 evader_track = np.zeros((track_length,eval_envs.world.num_oppo, 3))
    #                 for k in range(track_length):
    #                     for p in range(pursuer_track.shape[1]):
    #                         pursuer_track[k][p] = obs_array[i][j][k][0][p][0:3]
    #                     evader_track[k][0] = obs_array[i][j][k][0][0][3*eval_envs.world.num_team:]
    #                 folder_path = os.path.join(all_args.file_path, "pursuer_" + str(i) + " vs evader_" + str(j))
    #                 if not os.path.exists(folder_path):
    #                     os.makedirs(folder_path)
    #                     print("Folder created:", folder_path)
    #                 else:
    #                     print("Folder already exists:", folder_path)

    #                 print("save gif!")
    #                 get_track_gif(pursuer_track, evader_track, folder_path, info_array[i][j], "pursuer_" + str(i) + " vs evader_" + str(j))

    # else:
    #     runner.calu_win_prob(20)
    #     print("win_num: ", runner.total_pursuer_win , runner.total_evader_win)
    #     print("win_prob: ", runner.total_pursuer_win/runner.total_round)
    #     print("total_round: ", runner.total_round)
    #     print("pursuer policy: {}, evader policy: {}".format(all_args.pursuer_num,all_args.evader_num))

    # post process
    envs.close()
    if all_args.use_eval and eval_envs is not envs:
        eval_envs.close()

    print("use_wandb=",all_args.use_wandb)

    if all_args.use_wandb:
        run.finish()
    # else:
    #     runner.writter.export_scalars_to_json(str(runner.log_dir + '/summary.json'))
    #     runner.writter.close()


if __name__ == "__main__":
    main(sys.argv[1:])
