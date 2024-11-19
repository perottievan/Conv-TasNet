Instructions for running:

1. Create a new conda environment with python 3.6  
2. Use the command “conda install pytorch=0.4.1"  
3. Install [this](https://drive.google.com/file/d/15yyaspC7DpuiXuvv67Qc-2AQYBUA8RL6/view?usp=share_link) requirements.txt  
4. Clone the [project from github](https://github.com/kaituoxu/Conv-TasNet)  
5. From the root directory of the project, navigate to the egs/wsj0 directory.  
6. Edit the ‘data’ variable in run.sh to be the absolute path to the min directory of your wsj0-2mix dataset  
7. Run the run.sh file. This will start by preprocessing your data, then training, evaluating, and separating audio files. Logs for these can be found in subdirectories of the egs/wsj0 directory depending on the parameters used in run.sh.

If you have the WSJ0 dataset, but not the WSJ0-2mix, tools for constructing it from the WSJ0 dataset can be found at this page: [https://www.merl.com/research/highlights/deep-clustering](https://www.merl.com/research/highlights/deep-clustering).  
You will need matlab in order to use this tool.
