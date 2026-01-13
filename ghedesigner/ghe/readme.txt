This code is developed to enable GHEDesigner to take heat pump loads at input and do the processing to size the system.

We make use of GHEDesigner code but change how ground loads are handled. We do not have precomputed ground loads but rather calculate ground loads within the simulation. That is we change the simulated_detailed function in ground_heat_exchagers.py module

Works done here are:
1. Enable GHEDesigner to take heat pump loads as input, process them and size them.
2. We have tried four HP models: constant COP, lineaer (q_ext/q_htg, or q_rej/q_clg vary lineaery with EFT), quadratic model (ratios vary in quadratic realtion with EFT.), and linearized model where we use linear equation but determine coefficients based on previous EFT.

The code successfully performs the tasks. I made the commit and uploaded it to github.


ACTUALLY, I WAS SUPPOSED DO THIS 6-7 MONTHS AND I HAD DONE IT, BUT NOW I AM MAKING BETTER VERSION OF THE PROGRAM AND THIS IS SPECIFICALLY FOR THE "CONFERENCE PAPER" I AM WRITING.
