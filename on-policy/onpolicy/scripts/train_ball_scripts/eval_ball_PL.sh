#!/bin/sh
# exp param
env="BALL_A"
scenario="PlankNball"
algo="rmappo" # "mappo" "ippo"
exp="check"

# uav group param
num_agents=3 # two pursuers vs 1 evader

# train param
num_env_steps=0
# episode_length=400

# echo "n_rollout_threads: ${n_rollout_threads} \t ppo_epoch: ${ppo_epoch} \t num_mini_batch: ${num_mini_batch}"

CUDA_VISIBLE_DEVICES=0 python3 ../eval/eval_ball_PL.py \
--env_name ${env} --scenario_name ${scenario} --algorithm_name ${algo} --experiment_name ${exp} --seed 1 \
--num_agents ${num_agents} --num_env_steps ${num_env_steps} --n_rollout_threads 8 --ppo_epoch 15 --num_mini_batch 2 \
--save_interval 10 --log_interval 1 --n_eval_rollout_threads 2 --eval_episodes 100 --use_proper_time_limits \ #--use_render \
--user_name "leakycauldron" --wandb_name "first-trial" --d_k 8 --n_head 4 --sigma_layer_N 2 --layer_N 2 --encoder_layer_N 1 --hidden_size 128 --encoder_hidden_size 32 --attn_size 24 --recurrent_N 2 \
--critic_lr 0.00001 --lr 0.00001 --total_round 30 --use_mix_policy --population_size 17 --eval_episode_num 20 --channel_interval 1 --use_wandb \
--dir_player1 "/home/qiyuan/workspace/policy_backup/neupl_MFR_20240401/round80" --dir_player2 "/home/qiyuan/workspace/policy_backup/neupl_MFR_20240401/round80" --num_policy_p1 20 --num_policy_p2 25 \
--file_path "/home/qiyuan/workspace/plot/20240418" --use_track_recorder --begin_inx_p1 17 --begin_inx_p2 10
