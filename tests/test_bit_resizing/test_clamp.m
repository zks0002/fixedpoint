% Fixed point rounding stimulus generator
% Copyright 2020, Schweitzer Engineering Laboratories, Inc
% SEL Confidential

% Random seed
rng(str2num(getenv('FIXEDPOINTRANDOMSEED')));

% Number of stimulus items to generate
NUM_ITERATIONS = str2num(getenv('FIXEDPOINTNUMITERATIONS'));

overflows = {'Saturate'};

% Call the generic stimulus generator
test_overflow_handling(overflows, 'test_clamp', NUM_ITERATIONS);