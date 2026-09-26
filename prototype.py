"""
COUNTER BRAIDS - PROTOTIPNA IMPLEMENTACIJA
"""

import hashlib
import math
import random

def _hash1(value, key, modulo):
    data = f"{value}|{key}".encode()
    digest = hashlib.blake2b(data, digest_size=8).digest()
    return int.from_bytes(digest, "big") % modulo


def k_hash_edges(value, k, modulo, namespace=""):
    edges = []
    key = 0
    while len(edges) < k:
        c = _hash1(f"{namespace}:{value}", key, modulo)
        if c not in edges:
            edges.append(c)
        key += 1
        if key > 10 * (k + modulo):
            break
    return edges

def _rho(gamma, x):
    return math.exp(-gamma * (1 - x))


def _f_density_evolution(gamma, x, k, epsilon):
    inner = 1 - _rho(gamma, 1 - x)
    mid = 1 - _rho(gamma, 1 - inner ** (k - 1))
    return epsilon * mid ** (k - 1)


def _converges(gamma, k, epsilon, grid=400):
    for i in range(1, grid + 1):
        x = i / grid
        if _f_density_evolution(gamma, x, k, epsilon) >= x - 1e-9:
            return False
    return True


def density_evolution_threshold(k, epsilon):
    hi = 1.0
    while _converges(hi, k, epsilon):
        hi *= 2
        if hi > 1e6:
            break
    lo = 0.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if _converges(mid, k, epsilon):
            lo = mid
        else:
            hi = mid
    gamma_star = lo
    beta_star = k / gamma_star if gamma_star > 0 else float("inf")
    return gamma_star, beta_star

class CounterBraids:

    def __init__(self, n_flows, m1, m2, k=3, d1=5, d2=32):
        self.n = n_flows
        self.k = k
        self.m1 = m1
        self.m2 = m2
        self.d1 = d1
        self.d2 = d2
        self.base1 = 2 ** d1

        self.l1 = [0 for _ in range(self.m1)]
        self.l2 = [0 for _ in range(self.m2)]
        self.status = [False for _ in range(self.m1)]
        self.overflows = 0

    def flow_edges(self, flow):
        return k_hash_edges(flow, self.k, self.m1, namespace="flow")

    def carry_edges(self, counter):
        return k_hash_edges(counter, self.k, self.m2, namespace="carry")

    def packet(self, flow, verbose=False):
        edges = self.flow_edges(flow)
        if verbose:
            print(f"    packet for flow {flow!r}  ->  hashes to L1 counters {edges}")
        for c in edges:
            before = self.l1[c]
            self.l1[c] += 1
            if verbose:
                print(f"      L1[{c}]: {before} -> {self.l1[c]}", end="")
            if self.l1[c] >= self.base1:
                self.l1[c] -= self.base1
                self.status[c] = True
                self.overflows += 1
                carry_targets = self.carry_edges(c)
                if verbose:
                    print(f"   OVERFLOW (base={self.base1}) -> reset to {self.l1[c]}, "
                          f"status bit set, carry +1 to L2 counters {carry_targets}")
                for d in carry_targets:
                    self.l2[d] += 1
            elif verbose:
                print()

    def encode(self, flows, verbose=False):
        for flow, count in flows.items():
            if verbose:
                print(f"  flow {flow!r}: {count} packet(s)")
            for _ in range(count):
                self.packet(flow, verbose=verbose)

    @staticmethod
    def message_passing_decode(items, edges_fn, counter_values, min_value, iterations=20, verbose=False):

        items = list(items)
        edges = {i: edges_fn(i) for i in items}

        counter_to_items = {}
        for i in items:
            for a in edges[i]:
                counter_to_items.setdefault(a, []).append(i)

        nu = {(i, a): 0 for i in items for a in edges[i]}
        mu = {}

        if verbose:
            print(f"    {len(items)} item(s), {len(counter_to_items)} counter(s) touched, "
                  f"min_value={min_value}")
            estimate_history = {i: [] for i in items}

        for t in range(1, iterations + 1):

            new_mu = {}
            for a, connected in counter_to_items.items():
                ca = counter_values.get(a, 0)
                total = sum(nu[(j, a)] for j in connected)
                for i in connected:
                    val = ca - (total - nu[(i, a)])
                    new_mu[(a, i)] = max(val, min_value)
            mu = new_mu

            new_nu = {}
            for i in items:
                incident = edges[i]
                vals = [mu[(a, i)] for a in incident]
                if len(incident) == 1:
                    new_nu[(i, incident[0])] = vals[0]
                    continue
                for idx, a in enumerate(incident):
                    others = vals[:idx] + vals[idx + 1:]
                    new_nu[(i, a)] = min(others) if (t % 2 == 1) else max(others)
            nu = new_nu

            if verbose:
                # snapshot the current estimate for each item (same
                # rule as the final estimate, applied at this t)
                snapshot = {}
                for i in items:
                    vals = [mu[(a, i)] for a in edges[i]]
                    snapshot[i] = min(vals) if (t % 2 == 1) else max(vals)
                    estimate_history[i].append(snapshot[i])
                parity = "odd -> min" if t % 2 == 1 else "even -> max"
                shown = list(items)[:8]
                snap_str = ", ".join(f"{i}:{snapshot[i]}" for i in shown)
                more = "" if len(items) <= 8 else f", ... (+{len(items)-8} more)"
                print(f"    iter {t:2d} ({parity:9s})  estimates so far: {snap_str}{more}")

        f_hat = {}
        for i in items:
            vals = [mu[(a, i)] for a in edges[i]]
            f_hat[i] = min(vals) if (iterations % 2 == 1) else max(vals)

        if verbose:
            print(f"    converged after {iterations} iterations (see Table 1-style trace above)")

        return f_hat

    def decode(self, flows, iterations=20, verbose=False):

        overflowed = [c for c in range(self.m1) if self.status[c]]

        if verbose:
            print(f"  [layer 2] decoding overflow counts for {len(overflowed)} "
                  f"overflowed L1 counter(s) out of {self.m1}")

        f2_hat = self.message_passing_decode(
            items=overflowed,
            edges_fn=self.carry_edges,
            counter_values={i: v for i, v in enumerate(self.l2)},
            min_value=1,
            iterations=iterations,
            verbose=verbose
        )

        c1_corrected = {}
        for c in range(self.m1):
            if self.status[c]:
                c1_corrected[c] = self.l1[c] + f2_hat.get(c, 1) * self.base1
            else:
                c1_corrected[c] = self.l1[c]

        if verbose:
            print(f"  [layer 1] corrected counter values folded in "
                  f"(residual + overflow_count x {self.base1})")
            print(f"  [layer 1] decoding {len(flows)} flow sizes")

        f1_hat = self.message_passing_decode(
            items=flows.keys(),
            edges_fn=self.flow_edges,
            counter_values=c1_corrected,
            min_value=1,
            iterations=iterations,
            verbose=verbose
        )
        return f1_hat


def memory_bits(cb):
    return cb.m1 * (cb.d1 + 1) + cb.m2 * cb.d2


# ============================================================
# PARAMETER SELECTION
# ============================================================

def design_counter_braids(n, alpha, max_flow_size, k=3, safety_margin=1.2):

    epsilon = 2.0 ** (-alpha)
    gamma_star, beta_star = density_evolution_threshold(k, epsilon)
    beta_provisioned = beta_star * safety_margin

    m1 = max(1, math.ceil(beta_provisioned * n))
    m2 = max(1, math.ceil(0.1 * beta_provisioned * n))
    d1 = 5 if alpha >= 1.1 else 8
    d2 = max(8, math.ceil(math.log2(max(2, max_flow_size))) + 4)

    return {
        "epsilon": epsilon, "gamma_star": gamma_star, "beta_star": beta_star,
        "beta_provisioned": beta_provisioned,
        "m1": m1, "m2": m2, "k": k, "d1": d1, "d2": d2,
    }

def generate_flows_powerlaw(n, alpha=1.5, seed=0):
    rng = random.Random(seed)
    flows = {}
    for i in range(n):
        u = rng.random()
        f = math.floor((1 - u) ** (-1.0 / alpha))
        flows[i] = max(1, f)
    return flows

def evaluate(n, flows, design, iterations=20):
    cb = CounterBraids(n_flows=n, m1=design["m1"], m2=design["m2"],
                        k=design["k"], d1=design["d1"], d2=design["d2"])
    cb.encode(flows)
    f_hat = cb.decode(flows, iterations=iterations)

    errors = sum(1 for i in flows if f_hat.get(i) != flows[i])
    p_err = errors / n

    abs_errors = [abs(flows[i] - f_hat.get(i, 0)) for i in flows if f_hat.get(i) != flows[i]]
    e_m = (sum(abs_errors) / len(abs_errors)) if abs_errors else None

    r = memory_bits(cb) / n
    return {"p_err": p_err, "e_m": e_m, "r": r, "overflows": cb.overflows}


# ============================================================
# DEMO
# ============================================================

def run_toy_example():

    print("=" * 70)
    print("TOY EXAMPLE")
    print("=" * 70)

    toy_flows = {"flow1": 3, "flow2": 5, "flow3": 2}
    n = len(toy_flows)
    m1, m2, d1, k = 4, 3, 2, 2

    print(f"flows: {toy_flows}   (n={n})")
    print(f"m1={m1} L1 counters, m2={m2} L2 counters, d1={d1} bits "
          f"(overflow at {2**d1}), k={k} hash functions")

    cb = CounterBraids(n_flows=n, m1=m1, m2=m2, k=k, d1=d1, d2=8)

    print()
    print("-" * 70)
    print("ENCODING  (Exhibit 1: increment k hashed counters per packet,")
    print("           carry to L2 + set status bit on overflow)")
    print("-" * 70)
    cb.encode(toy_flows, verbose=True)

    print()
    print(f"final L1 counters: {cb.l1}")
    print(f"final status bits: {cb.status}")
    print(f"final L2 counters: {cb.l2}")
    print(f"total overflow events: {cb.overflows}")

    print()
    print("-" * 70)
    print("DECODING  (Exhibit 3: layer 2 first, then layer 1 -")
    print("           Exhibit 2's message passing within each layer)")
    print("-" * 70)
    f_hat = cb.decode(toy_flows, iterations=6, verbose=True)

    print()
    print("-" * 70)
    print("RESULT")
    print("-" * 70)
    for flow, true_size in toy_flows.items():
        estimate = f_hat.get(flow)
        mark = "OK" if estimate == true_size else "MISMATCH"
        print(f"  flow {flow!r}: true size = {true_size:2d}   decoded = {estimate!s:>3}   [{mark}]")
    print()


def main():

    run_toy_example()

    n = 1000
    alpha = 1.5
    max_flow_size = 300

    design = design_counter_braids(n, alpha, max_flow_size, k=3, safety_margin=1.2)

    print("=" * 70)
    print("DESIGN  (Theorem 2 + Section 6 rules of thumb)")
    print("=" * 70)
    print(f"n = {n} flows, alpha = {alpha}, max flow size assumed = {max_flow_size}")
    print(f"epsilon = P(f>1)     = {design['epsilon']:.3f}")
    print(f"beta*                = {design['beta_star']:.3f}  (density evolution threshold)")
    print(f"provisioned beta1    = {design['beta_provisioned']:.3f}  (beta* x 1.20 safety margin)")
    print(f"m1 = {design['m1']}, m2 = {design['m2']}, d1 = {design['d1']}, d2 = {design['d2']}, k = {design['k']}")

    # single run
    flows = generate_flows_powerlaw(n, alpha=alpha, seed=42)
    result = evaluate(n, flows, design)
    reduction = (1 - result["r"] / 16) * 100

    print()
    print("=" * 70)
    print("RESULT (single run)")
    print("=" * 70)
    print(f"Perr (fraction reconstructed incorrectly) = {result['p_err']:.2%}")
    print(f"r (space, bits/flow)                      = {result['r']:.2f}")
    print(f"memory reduction vs. naive 16-bit/flow     = {reduction:.1f}%")

    # robustness check across many independent random traffic samples
    trials = 30
    fails = 0
    for seed in range(trials):
        flows = generate_flows_powerlaw(n, alpha=alpha, seed=seed)
        r = evaluate(n, flows, design)
        if r["p_err"] > 0:
            fails += 1

    print()
    print("=" * 70)
    print(f"ROBUSTNESS CHECK ({trials} independent random traffic samples)")
    print("=" * 70)
    print(f"failures: {fails}/{trials}")
    print(f"-> {'100% exact reconstruction, every time' if fails == 0 else 'not fully reliable at this margin'}, "
          f"at {reduction:.1f}% memory savings vs. a naive per-flow counter.")


if __name__ == "__main__":
    main()