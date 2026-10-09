from simulator.benchmark.protocol import TOKENS as COARSE_TOKENS

FINE_TOKENS = tuple(t+"_FINE" for t in COARSE_TOKENS if t not in ("STILL", "GRASP", "RELEASE"))
TOKENS = COARSE_TOKENS+FINE_TOKENS
