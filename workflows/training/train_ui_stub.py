"""训练模块入口。

该入口转发到单帧 MLP 训练脚本，便于采集后直接执行训练。
"""

from workflows.training.train_single_frame_mlp import main


if __name__ == "__main__":
    main()
