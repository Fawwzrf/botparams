import os
import json
import time
import subprocess
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime, timezone

# ==============================================================================
# 1. KONFIGURASI GLOBAL V5.0 (8-PARAMETER GRID MATRIX OPTIMIZER)
# ==============================================================================
INITIAL_BALANCE = 12.50
MAX_OPEN_POSITIONS = 4
BASE_DEX_FEE = 0.003
LOG_FILE = "hasil_v5_params.txt"
STATE_FILE = "state_v5_params.json"
STATE_VERSION = "V5_PARAM_MATRIX_8"
MAX_RUNTIME_SECONDS = 18000     # 5 Jam per sesi GitHub Actions

SOL_MINT = "So11111111111111111111111111111111111111112"

_retry = Retry(total=2, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
_adapter = HTTPAdapter(max_retries=_retry, pool_connections=20, pool_maxsize=20)
SESSION = requests.Session()
SESSION.mount('https://', _adapter)
SESSION.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/json'
})
REQUEST_TIMEOUT = 10

audit_cache = {}
global_scam_blacklist = set()
first_seen_prices = {}
sol_macro_state = {'price': 0.0, 'm5': 0.0, 'h1': 0.0, 'is_crashing': False}

# ==============================================================================
# 2. DEFINISI 8 VARIAN PARAMETER (4 VORTEX + 4 CHRONOS ADAPTIVE)
# ==============================================================================
COMPETITORS = [
    'VORTEX_P1_SNIPER',
    'VORTEX_P2_BALANCED',
    'VORTEX_P3_MOONBAG',
    'VORTEX_P4_SCALPER',
    'CHRONOS_P1_FORTRESS',
    'CHRONOS_P2_STANDARD',
    'CHRONOS_P3_AGGRESSIVE',
    'CHRONOS_P4_SWING'
]

# --- 4 RACIKAN STATIS M5 VORTEX ---
VORTEX_PARAMS = {
    'VORTEX_P1_SNIPER': {
        'session_name': 'VORTEX_SNIPER_TIGHT',
        'alloc': 0.25, 'min_liq': 18000, 'max_rug_score': 380,
        'min_bs': 1.85, 'min_buys': 52, 'min_avg_tx': 25.0, 'max_fdv_liq': 8.0,
        'min_m5': 3.5, 'max_m5': 25.0, 'min_dpp': 0.030, 'min_liq_growth': 0.6,
        'pb_min': 1.0, 'pb_max': 6.0,
        'hard_sl': -8.5, 'be_trig': 6.5, 'be_lock': 2.2,
        'tp1_pct': 10.5, 'tp1_sell': 0.65, 'tp2_pct': 30.0, 'tp2_sell': 0.50,
        'base_trail': 0.07, 'tight_trail': 0.04, 'stagnant_m': 5.0
    },
    'VORTEX_P2_BALANCED': {
        'session_name': 'VORTEX_BALANCED_CORE',
        'alloc': 0.25, 'min_liq': 15000, 'max_rug_score': 480,
        'min_bs': 1.70, 'min_buys': 45, 'min_avg_tx': 22.0, 'max_fdv_liq': 9.0,
        'min_m5': 3.0, 'max_m5': 28.0, 'min_dpp': 0.022, 'min_liq_growth': 0.3,
        'pb_min': 1.0, 'pb_max': 7.5,
        'hard_sl': -11.0, 'be_trig': 8.0, 'be_lock': 2.2,
        'tp1_pct': 12.5, 'tp1_sell': 0.55, 'tp2_pct': 38.0, 'tp2_sell': 0.50,
        'base_trail': 0.08, 'tight_trail': 0.05, 'stagnant_m': 6.5
    },
    'VORTEX_P3_MOONBAG': {
        'session_name': 'VORTEX_MOONBAG_RUNNER',
        'alloc': 0.25, 'min_liq': 15000, 'max_rug_score': 460,
        'min_bs': 1.75, 'min_buys': 45, 'min_avg_tx': 22.0, 'max_fdv_liq': 9.0,
        'min_m5': 3.0, 'max_m5': 30.0, 'min_dpp': 0.022, 'min_liq_growth': 0.4,
        'pb_min': 1.5, 'pb_max': 8.0,
        'hard_sl': -12.0, 'be_trig': 8.5, 'be_lock': 2.0,
        'tp1_pct': 19.0, 'tp1_sell': 0.35, 'tp2_pct': 55.0, 'tp2_sell': 0.45,
        'base_trail': 0.12, 'tight_trail': 0.08, 'stagnant_m': 8.5
    },
    'VORTEX_P4_SCALPER': {
        'session_name': 'VORTEX_HF_SCALPER',
        'alloc': 0.32, 'min_liq': 11000, 'max_rug_score': 500,
        'min_bs': 1.55, 'min_buys': 36, 'min_avg_tx': 16.0, 'max_fdv_liq': 11.0,
        'min_m5': 2.5, 'max_m5': 32.0, 'min_dpp': 0.015, 'min_liq_growth': 0.1,
        'pb_min': 0.8, 'pb_max': 8.0,
        'hard_sl': -10.0, 'be_trig': 7.0, 'be_lock': 2.0,
        'tp1_pct': 11.5, 'tp1_sell': 0.60, 'tp2_pct': 34.0, 'tp2_sell': 0.55,
        'base_trail': 0.08, 'tight_trail': 0.04, 'stagnant_m': 4.5
    }
}

# --- 4 RACIKAN DINAMIS CHRONOS ADAPTIVE (OTOMATIS MENYESUAIKAN JAM UTC) ---
def get_chronos_base_session(utc_hour):
    if 0 <= utc_hour < 7:
        return {
            'session_name': 'S1_ASIA',
            'alloc': 0.25, 'min_liq': 15000, 'max_rug_score': 450,
            'min_bs': 1.75, 'min_buys': 48, 'min_avg_tx': 22.0, 'max_fdv_liq': 8.5,
            'min_m5': 3.0, 'max_m5': 26.0, 'min_dpp': 0.024, 'min_liq_growth': 0.4,
            'pb_min': 1.0, 'pb_max': 7.0,
            'hard_sl': -10.5, 'be_trig': 7.5, 'be_lock': 2.2,
            'tp1_pct': 12.0, 'tp1_sell': 0.60, 'tp2_pct': 35.0, 'tp2_sell': 0.50,
            'base_trail': 0.08, 'tight_trail': 0.05, 'stagnant_m': 5.5
        }
    elif 7 <= utc_hour < 13:
        return {
            'session_name': 'S2_EURO',
            'alloc': 0.25, 'min_liq': 14500, 'max_rug_score': 480,
            'min_bs': 1.80, 'min_buys': 50, 'min_avg_tx': 20.0, 'max_fdv_liq': 10.0,
            'min_m5': 3.5, 'max_m5': 34.0, 'min_dpp': 0.018, 'min_liq_growth': 0.2,
            'pb_min': 1.0, 'pb_max': 6.5,
            'hard_sl': -11.0, 'be_trig': 8.5, 'be_lock': 2.2,
            'tp1_pct': 17.5, 'tp1_sell': 0.55, 'tp2_pct': 45.0, 'tp2_sell': 0.50,
            'base_trail': 0.09, 'tight_trail': 0.05, 'stagnant_m': 6.5
        }
    elif 13 <= utc_hour < 17:
        return {
            'session_name': 'S3_US_PEAK',
            'alloc': 0.25, 'min_liq': 16000, 'max_rug_score': 480,
            'min_bs': 1.65, 'min_buys': 45, 'min_avg_tx': 22.0, 'max_fdv_liq': 9.5,
            'min_m5': 3.5, 'max_m5': 35.0, 'min_dpp': 0.020, 'min_liq_growth': 0.2,
            'pb_min': 2.2, 'pb_max': 8.5,
            'hard_sl': -11.5, 'be_trig': 9.0, 'be_lock': 2.2,
            'tp1_pct': 20.0, 'tp1_sell': 0.50, 'tp2_pct': 52.0, 'tp2_sell': 0.50,
            'base_trail': 0.10, 'tight_trail': 0.06, 'stagnant_m': 7.5
        }
    else:
        return {
            'session_name': 'S4_NIGHT',
            'alloc': 0.20, 'min_liq': 18500, 'max_rug_score': 350,
            'min_bs': 1.90, 'min_buys': 55, 'min_avg_tx': 25.0, 'max_fdv_liq': 8.0,
            'min_m5': 3.5, 'max_m5': 24.0, 'min_dpp': 0.030, 'min_liq_growth': 1.0,
            'pb_min': 1.0, 'pb_max': 6.0,
            'hard_sl': -9.5, 'be_trig': 7.0, 'be_lock': 2.5,
            'tp1_pct': 11.0, 'tp1_sell': 0.65, 'tp2_pct': 32.0, 'tp2_sell': 0.50,
            'base_trail': 0.07, 'tight_trail': 0.04, 'stagnant_m': 5.0
        }

def get_competitor_config(v_name, utc_hour):
    """Mengambil konfigurasi spesifik untuk masing-masing dari 8 kompetitor."""
    if v_name in VORTEX_PARAMS:
        return VORTEX_PARAMS[v_name]

    cfg = dict(get_chronos_base_session(utc_hour))

    if v_name == 'CHRONOS_P1_FORTRESS':
        # Lebih defensif: likuiditas lebih tebal, SL ketat, BE & TP lebih cepat
        cfg['session_name'] += '_FORTRESS'
        cfg['alloc'] = 0.22
        cfg['min_liq'] += 4000
        cfg['max_rug_score'] = min(cfg['max_rug_score'], 360)
        cfg['min_bs'] += 0.12
        cfg['min_dpp'] += 0.005
        cfg['hard_sl'] = max(cfg['hard_sl'], -9.0)
        cfg['be_trig'] = max(6.2, cfg['be_trig'] - 1.5)
        cfg['tp1_pct'] = max(10.0, cfg['tp1_pct'] - 2.5)
        cfg['tp1_sell'] = 0.65

    elif v_name == 'CHRONOS_P2_STANDARD':
        cfg['session_name'] += '_STD'

    elif v_name == 'CHRONOS_P3_AGGRESSIVE':
        # Compounding agresif saat sesi Eropa & Amerika, filter sedikit lebih cepat masuk
        cfg['session_name'] += '_AGGR'
        cfg['alloc'] = 0.35 if (7 <= utc_hour < 17) else 0.22
        cfg['min_bs'] = max(1.55, cfg['min_bs'] - 0.10)
        cfg['min_dpp'] = max(0.015, cfg['min_dpp'] - 0.004)
        cfg['be_trig'] = max(6.8, cfg['be_trig'] - 1.0)
        cfg['tp1_sell'] = 0.60

    elif v_name == 'CHRONOS_P4_SWING':
        # Target profit lebih jauh untuk menangkap multi-wave runner
        cfg['session_name'] += '_SWING'
        cfg['pb_max'] = min(9.5, cfg['pb_max'] + 1.5)
        cfg['hard_sl'] = min(-12.5, cfg['hard_sl'] - 1.0)
        cfg['tp1_pct'] += 5.0
        cfg['tp1_sell'] = 0.40
        cfg['tp2_pct'] += 12.0
        cfg['base_trail'] += 0.02
        cfg['tight_trail'] += 0.02
        cfg['stagnant_m'] += 2.0

    return cfg

engines = {}
total_elapsed_sec = 0.0

def write_log(text):
    print(text, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(text + "\n")

def calc_dynamic_slippage(order_usd, liq_usd):
    if liq_usd <= 0:
        return 0.005
    price_impact = (order_usd / liq_usd) * 2.0
    return min(0.025, BASE_DEX_FEE + price_impact)

# ==============================================================================
# 3. SISTEM CHECKPOINT & LIVE GITHUB SYNC
# ==============================================================================
def init_or_load_state():
    global engines, global_scam_blacklist, first_seen_prices, total_elapsed_sec
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if saved.get('version') == STATE_VERSION:
                total_elapsed_sec = saved.get('total_elapsed_sec', 0.0)
                global_scam_blacklist = set(saved.get('global_scam_blacklist', []))
                first_seen_prices = saved.get('first_seen_prices', {})
                for v_name in COMPETITORS:
                    s_eng = saved.get('engines', {}).get(v_name, {})
                    engines[v_name] = {
                        'cash_usd': s_eng.get('cash_usd', INITIAL_BALANCE),
                        'positions': s_eng.get('positions', {}),
                        'watchlist': s_eng.get('watchlist', {}),
                        'traded_tokens': set(s_eng.get('traded_tokens', [])),
                        'wins': s_eng.get('wins', 0),
                        'losses': s_eng.get('losses', 0),
                        'gross_profit': s_eng.get('gross_profit', 0.0),
                        'gross_loss': s_eng.get('gross_loss', 0.0),
                        'peak_equity': s_eng.get('peak_equity', INITIAL_BALANCE),
                        'max_dd_pct': s_eng.get('max_dd_pct', 0.0),
                        'consec_losses': s_eng.get('consec_losses', 0),
                        'cooldown_until': s_eng.get('cooldown_until', 0.0)
                    }
                write_log(f"♻️ [CHECKPOINT V5 LOADED] Melanjutkan optimasi 8 parameter (Durasi: {total_elapsed_sec/3600:.2f} Jam)")
                return
        except Exception as e:
            write_log(f"[WARNING] Memulai state V5 baru: {e}")

    for v_name in COMPETITORS:
        engines[v_name] = {
            'cash_usd': INITIAL_BALANCE, 'positions': {}, 'watchlist': {},
            'traded_tokens': set(), 'wins': 0, 'losses': 0, 'gross_profit': 0.0,
            'gross_loss': 0.0, 'peak_equity': INITIAL_BALANCE, 'max_dd_pct': 0.0,
            'consec_losses': 0, 'cooldown_until': 0.0
        }

def save_state(session_elapsed, push_to_git=False):
    serializable_engines = {}
    for v_name, eng in engines.items():
        serializable_engines[v_name] = {
            'cash_usd': eng['cash_usd'],
            'positions': eng['positions'],
            'watchlist': eng['watchlist'],
            'traded_tokens': list(eng['traded_tokens']),
            'wins': eng['wins'],
            'losses': eng['losses'],
            'gross_profit': eng['gross_profit'],
            'gross_loss': eng['gross_loss'],
            'peak_equity': eng['peak_equity'],
            'max_dd_pct': eng['max_dd_pct'],
            'consec_losses': eng['consec_losses'],
            'cooldown_until': eng['cooldown_until']
        }
    if len(first_seen_prices) > 1500:
        keys_to_keep = list(first_seen_prices.keys())[-1000:]
        trimmed_seen = {k: first_seen_prices[k] for k in keys_to_keep}
    else:
        trimmed_seen = first_seen_prices

    data = {
        'version': STATE_VERSION,
        'total_elapsed_sec': total_elapsed_sec + session_elapsed,
        'global_scam_blacklist': list(global_scam_blacklist),
        'first_seen_prices': trimmed_seen,
        'engines': serializable_engines
    }
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)

    if push_to_git:
        try:
            subprocess.run(["git", "add", LOG_FILE, STATE_FILE], check=False)
            subprocess.run(["git", "commit", "-m", f"V5 Params sync {((total_elapsed_sec + session_elapsed)/3600):.2f}h"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "pull", "--rebase", "-X", "theirs", "origin", "main"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "push", "origin", "main"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

# ==============================================================================
# 4. AUDIT KONTRAK, MACRO SOL MONITOR, & WIDE-SPECTRUM RADAR (90 TOKENS)
# ==============================================================================
def verify_contract_safety(token_address, max_allowed_score=480):
    if token_address in global_scam_blacklist:
        return False, 9999, "Blacklisted"
    if token_address in audit_cache:
        is_ok, score, msg = audit_cache[token_address]
        if not is_ok or score > max_allowed_score:
            return False, score, msg
        return True, score, msg

    try:
        url = f"https://api.rugcheck.xyz/v1/tokens/{token_address}/report/summary"
        resp = SESSION.get(url, timeout=6)
        if resp.status_code != 200:
            return False, 9999, "Audit tidak tersedia"
        data = resp.json()
        score = data.get('score', 9999)
        for r in data.get('risks', []):
            level = r.get('level', '')
            name = r.get('name', '').lower()
            if level == 'danger' or 'mint' in name or 'freeze' in name or 'honeypot' in name:
                res = (False, score, f"Bahaya: {r.get('name')}")
                audit_cache[token_address] = res
                global_scam_blacklist.add(token_address)
                return res
        if score > 520:
            res = (False, score, f"Skor Tinggi ({score})")
            audit_cache[token_address] = res
            global_scam_blacklist.add(token_address)
            return res

        res = (True, score, f"Aman (Skor: {score})")
        audit_cache[token_address] = res
        if score > max_allowed_score:
            return False, score, f"Skor > Batas ({score})"
        return res
    except Exception as e:
        return False, 9999, f"Error Audit: {e}"

def update_sol_macro_status():
    global sol_macro_state
    try:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{SOL_MINT}"
        resp = SESSION.get(url, timeout=6)
        if resp.status_code == 200:
            pairs = [p for p in resp.json().get('pairs', []) if p.get('chainId') == 'solana' and p.get('quoteToken', {}).get('symbol') in ['USDC', 'USDT']]
            if pairs:
                pairs.sort(key=lambda x: x.get('liquidity', {}).get('usd', 0), reverse=True)
                main_sol = pairs[0]
                price = float(main_sol.get('priceUsd', 0) or 0)
                m5 = float(main_sol.get('priceChange', {}).get('m5', 0) or 0)
                h1 = float(main_sol.get('priceChange', {}).get('h1', 0) or 0)
                is_crash = (m5 <= -2.5) or (h1 <= -4.5)
                sol_macro_state = {'price': price, 'm5': m5, 'h1': h1, 'is_crashing': is_crash}
    except Exception:
        pass

def fetch_shared_market_data(cycle):
    if cycle % 5 == 1:
        update_sol_macro_status()

    token_addrs = []
    best_pairs_by_token = {}

    endpoints = [
        "https://api.dexscreener.com/token-profiles/latest/v1",
        "https://api.dexscreener.com/token-boosts/latest/v1",
        "https://api.dexscreener.com/token-boosts/top/v1"
    ]
    for url in endpoints:
        try:
            resp = SESSION.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                for item in resp.json():
                    if item.get('chainId') == 'solana':
                        addr = item.get('tokenAddress')
                        if addr and addr not in token_addrs and addr not in global_scam_blacklist:
                            token_addrs.append(addr)
        except Exception:
            pass

    organic_queries = ["pump", "raydium", "meteora", "solana"]
    q = organic_queries[cycle % len(organic_queries)]
    try:
        resp = SESSION.get(f"https://api.dexscreener.com/latest/dex/search?q={q}", timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            for p in resp.json().get('pairs', []):
                if p.get('chainId') == 'solana':
                    t_addr = p['baseToken']['address']
                    if t_addr in global_scam_blacklist or t_addr == SOL_MINT:
                        continue
                    liq = p.get('liquidity', {}).get('usd', 0)
                    if t_addr not in best_pairs_by_token or liq > best_pairs_by_token[t_addr].get('liquidity', {}).get('usd', 0):
                        best_pairs_by_token[t_addr] = p
    except Exception:
        pass

    watchlist_addrs = set()
    for eng in engines.values():
        watchlist_addrs.update(eng['watchlist'].keys())

    combined_tokens = list(watchlist_addrs) + [a for a in token_addrs if a not in watchlist_addrs]
    combined_tokens = combined_tokens[:90]

    for i in range(0, len(combined_tokens), 30):
        batch = combined_tokens[i:i+30]
        if not batch:
            continue
        try:
            tokens_csv = ",".join(batch)
            resp = SESSION.get(f"https://api.dexscreener.com/latest/dex/tokens/{tokens_csv}", timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                for p in resp.json().get('pairs', []):
                    if p.get('chainId') != 'solana':
                        continue
                    t_addr = p['baseToken']['address']
                    liq = p.get('liquidity', {}).get('usd', 0)
                    if t_addr not in best_pairs_by_token or liq > best_pairs_by_token[t_addr].get('liquidity', {}).get('usd', 0):
                        best_pairs_by_token[t_addr] = p
        except Exception:
            pass

    for t_addr, pair in best_pairs_by_token.items():
        p_usd = float(pair.get('priceUsd', 0) or 0)
        if p_usd > 0 and t_addr not in first_seen_prices:
            first_seen_prices[t_addr] = p_usd

    open_pair_addrs = set()
    for eng in engines.values():
        open_pair_addrs.update(eng['positions'].keys())

    open_pairs_data = {}
    if open_pair_addrs:
        try:
            pairs_csv = ",".join(list(open_pair_addrs)[:30])
            resp = SESSION.get(f"https://api.dexscreener.com/latest/dex/pairs/solana/{pairs_csv}", timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                for p in resp.json().get('pairs', []):
                    if 'pairAddress' in p:
                        open_pairs_data[p['pairAddress']] = p
        except Exception:
            pass

    return best_pairs_by_token, open_pairs_data

# ==============================================================================
# 5. MESIN EVALUASI POSISI & EKSEKUSI 8 PARAMETER V5
# ==============================================================================
def get_total_equity(v_name):
    eng = engines[v_name]
    locked_usd = sum(p['invested_usd'] * (p['tokens'] / p['init_tokens']) for p in eng['positions'].values())
    return eng['cash_usd'] + locked_usd

def close_variant_position(v_name, pair_addr, curr_price, curr_liq, reason):
    eng = engines[v_name]
    pos = eng['positions'][pair_addr]
    raw_usd = pos['tokens'] * curr_price
    slip = calc_dynamic_slippage(raw_usd, curr_liq)
    remaining_usd = raw_usd * (1 - slip)
    eng['cash_usd'] += remaining_usd

    total_returned = pos['realized_usd'] + remaining_usd
    net_profit = total_returned - pos['invested_usd']
    roi_pct = (net_profit / pos['invested_usd']) * 100
    now_ts = datetime.now(timezone.utc).timestamp()

    eng['traded_tokens'].add(pos['token_address'])

    if net_profit >= 0:
        eng['wins'] += 1
        eng['gross_profit'] += net_profit
        eng['consec_losses'] = 0
    else:
        eng['losses'] += 1
        eng['gross_loss'] += abs(net_profit)
        eng['consec_losses'] += 1
        global_scam_blacklist.add(pos['token_address'])
        if eng['consec_losses'] >= 2:
            eng['cooldown_until'] = now_ts + 1200
            write_log(f"🛡️ [{v_name}] Cooldown 20m Aktif (Proteksi Pasar Buruk)")

    del eng['positions'][pair_addr]

    tot_eq = get_total_equity(v_name)
    if tot_eq > eng['peak_equity']:
        eng['peak_equity'] = tot_eq
    dd = ((eng['peak_equity'] - tot_eq) / eng['peak_equity']) * 100
    if dd > eng['max_dd_pct']:
        eng['max_dd_pct'] = dd

    tot_t = eng['wins'] + eng['losses']
    wr = (eng['wins'] / tot_t) * 100 if tot_t > 0 else 0.0
    growth = ((tot_eq - INITIAL_BALANCE) / INITIAL_BALANCE) * 100

    now_str = datetime.now().strftime('%H:%M:%S')
    write_log(
        f"🏁 [{now_str}] [{v_name:<21}] {reason:<18} | {pos['symbol']:<10} | "
        f"PnL: {net_profit:+.2f} USD ({roi_pct:+.1f}%) | "
        f"Ekuitas: ${tot_eq:.2f} ({growth:+.1f}%) | WR: {eng['wins']}W/{eng['losses']}L ({wr:.0f}%)"
    )

def process_competitor(v_name, best_pairs_by_token, open_pairs_data):
    eng = engines[v_name]
    now_dt = datetime.now(timezone.utc)
    now_ts = now_dt.timestamp()
    now_ms = now_ts * 1000

    cfg = get_competitor_config(v_name, now_dt.hour)
    s_name = cfg['session_name']

    # A. KAWAL POSISI AKTIF
    for p_addr, pos in list(eng['positions'].items()):
        p_data = open_pairs_data.get(p_addr) or best_pairs_by_token.get(pos['token_address'])
        if not p_data:
            continue

        curr_price = float(p_data.get('priceUsd', pos['entry_price']))
        curr_liq = p_data.get('liquidity', {}).get('usd', pos['entry_liq'])
        txns_5m = p_data.get('txns', {}).get('m5', {})
        buys = txns_5m.get('buys', 1)
        sells = max(1, txns_5m.get('sells', 1))
        bs_ratio = buys / sells

        if curr_price > pos['highest_price']:
            pos['highest_price'] = curr_price

        pnl_pct = ((curr_price - pos['entry_price']) / pos['entry_price']) * 100
        max_pnl_pct = ((pos['highest_price'] - pos['entry_price']) / pos['entry_price']) * 100
        drop_from_peak = (pos['highest_price'] - curr_price) / pos['highest_price']
        liq_drop = (pos['entry_liq'] - curr_liq) / pos['entry_liq']
        hold_mins = (now_ts - pos['entry_time']) / 60.0

        # 3-Stage Ratchet Lock
        if max_pnl_pct >= cfg['be_trig'] and not pos['breakeven_locked']:
            pos['breakeven_locked'] = True
            pos['dynamic_sl_pct'] = max(pos['dynamic_sl_pct'], cfg['be_lock'])
        if max_pnl_pct >= 32.0:
            pos['dynamic_sl_pct'] = max(pos['dynamic_sl_pct'], 20.0)
        elif max_pnl_pct >= 18.0:
            pos['dynamic_sl_pct'] = max(pos['dynamic_sl_pct'], 9.0)

        # 1. Anti-Rugpull Exit
        if liq_drop >= 0.11 or (sells > buys * 2.1 and pnl_pct < -3.5):
            close_variant_position(v_name, p_addr, curr_price, curr_liq, "🚨 ANTI-RUG EXIT")
            continue

        # 2. Take Profit Tier 1
        if pnl_pct >= cfg['tp1_pct'] and not pos['tp1_hit']:
            sell_tokens = pos['tokens'] * cfg['tp1_sell']
            pos['tokens'] -= sell_tokens
            raw_usd = sell_tokens * curr_price
            net_usd = raw_usd * (1 - calc_dynamic_slippage(raw_usd, curr_liq))
            eng['cash_usd'] += net_usd
            pos['realized_usd'] += net_usd
            pos['tp1_hit'] = True
            pos['breakeven_locked'] = True
            pos['dynamic_sl_pct'] = max(pos['dynamic_sl_pct'], 3.0)
            write_log(f"💵 [{v_name:<21}] TP-1 (+{pnl_pct:.1f}%) pada {pos['symbol']} | Cair: +${net_usd:.2f}")

        # 3. Take Profit Tier 2
        if pnl_pct >= cfg['tp2_pct'] and not pos['tp2_hit']:
            sell_tokens = pos['tokens'] * cfg['tp2_sell']
            pos['tokens'] -= sell_tokens
            raw_usd = sell_tokens * curr_price
            net_usd = raw_usd * (1 - calc_dynamic_slippage(raw_usd, curr_liq))
            eng['cash_usd'] += net_usd
            pos['realized_usd'] += net_usd
            pos['tp2_hit'] = True
            write_log(f"🔥 [{v_name:<21}] TP-2 (+{pnl_pct:.1f}%) pada {pos['symbol']} | Cair: +${net_usd:.2f}")

        # 4. Time-Stop
        if hold_mins >= cfg['stagnant_m'] and pnl_pct < 4.0 and bs_ratio < 1.25:
            close_variant_position(v_name, p_addr, curr_price, curr_liq, "⏳ TIME-STOP")
            continue

        # 5. Trailing Stop
        active_trail = cfg['tight_trail'] if pos['tp1_hit'] else cfg['base_trail']
        if max_pnl_pct >= 10.5 and drop_from_peak >= active_trail and pnl_pct >= 1.5:
            close_variant_position(v_name, p_addr, curr_price, curr_liq, "🎯 TRAILING PROFIT")
            continue

        # 6. 2-Tick Confirmed Stop Loss
        if pnl_pct <= pos['dynamic_sl_pct']:
            pos['sl_breach_ticks'] = pos.get('sl_breach_ticks', 0) + 1
            if pos['breakeven_locked'] or pos['sl_breach_ticks'] >= 2 or bs_ratio < 0.85 or pnl_pct <= (cfg['hard_sl'] * 1.3):
                reason = "🛡️ RATCHET/BE PROFIT" if pos['breakeven_locked'] else "❌ HARD STOP LOSS"
                close_variant_position(v_name, p_addr, curr_price, curr_liq, reason)
                continue
        else:
            pos['sl_breach_ticks'] = 0

    # B. CEK MACRO SOL CRASH & COOLDOWN
    if sol_macro_state['is_crashing'] or now_ts < eng['cooldown_until']:
        return

    for t_addr in list(eng['watchlist'].keys()):
        if now_ts - eng['watchlist'][t_addr]['added_time'] > 600:
            del eng['watchlist'][t_addr]

    if len(eng['positions']) >= MAX_OPEN_POSITIONS or eng['cash_usd'] < 1.8:
        return

    # C. PINDAI KANDIDAT & EKSEKUSI
    audits_this_cycle = 0
    for token_addr, pair in best_pairs_by_token.items():
        if len(eng['positions']) >= MAX_OPEN_POSITIONS:
            break
        pair_addr = pair.get('pairAddress')
        symbol = pair['baseToken']['symbol']

        if token_addr in global_scam_blacklist or token_addr in eng['traded_tokens'] or pair_addr in eng['positions']:
            continue

        created_at = pair.get('pairCreatedAt', 0)
        age_minutes = (now_ms - created_at) / 60000.0 if created_at else 9999
        liq_usd = pair.get('liquidity', {}).get('usd', 0)
        fdv_usd = pair.get('fdv', 0) or liq_usd * 2
        price_usd = float(pair.get('priceUsd', 0) or 0)

        max_allowed_age = 240 if liq_usd >= 22000 else 120
        if liq_usd < cfg['min_liq'] or age_minutes > max_allowed_age or price_usd <= 0:
            continue

        first_price = first_seen_prices.get(token_addr, price_usd)
        if ((price_usd - first_price) / first_price) * 100 > 38.0:
            continue

        txns_5m = pair.get('txns', {}).get('m5', {})
        buys_5m = txns_5m.get('buys', 0)
        sells_5m = max(1, txns_5m.get('sells', 1))
        vol_5m = pair.get('volume', {}).get('m5', 0)

        m5_chg = float(pair.get('priceChange', {}).get('m5', 0) or 0)
        h1_chg = float(pair.get('priceChange', {}).get('h1', 0) or 0)

        bs_ratio = buys_5m / sells_5m
        vol_to_liq = vol_5m / liq_usd
        avg_tx_usd = vol_5m / max(1, (buys_5m + sells_5m))
        fdv_to_liq = fdv_usd / liq_usd
        dpp_absorption = (vol_5m / max(1.0, abs(m5_chg))) / liq_usd

        # TAHAP 2: EVALUASI WATCHLIST
        if token_addr in eng['watchlist']:
            w = eng['watchlist'][token_addr]
            w['checks'] += 1
            if price_usd > w['peak_price']:
                w['peak_price'] = price_usd

            pullback_pct = ((w['peak_price'] - price_usd) / w['peak_price']) * 100
            liq_growth_pct = ((liq_usd - w['init_liq']) / w['init_liq']) * 100

            if bs_ratio < 1.35 or m5_chg < 2.5 or liq_usd < w['init_liq'] * 0.96:
                del eng['watchlist'][token_addr]
                continue

            trigger_buy = False
            trigger_desc = ""

            is_vortex_valid = (
                dpp_absorption >= cfg['min_dpp'] and
                liq_growth_pct >= cfg['min_liq_growth'] and
                bs_ratio >= cfg['min_bs'] and
                pullback_pct <= cfg['pb_max']
            )
            if is_vortex_valid:
                trigger_buy = True
                trigger_desc = f"Vortex (DPP {dpp_absorption:.3f} | Liq +{liq_growth_pct:.1f}%)"

            if not trigger_buy and v_name.startswith('CHRONOS_'):
                if 'S2_EURO' in s_name:
                    if price_usd > w['last_price'] and buys_5m > w['last_buys'] and bs_ratio >= cfg['min_bs'] and liq_growth_pct >= 0.1 and pullback_pct <= 5.5:
                        trigger_buy = True
                        trigger_desc = f"Euro Accel (B/S {bs_ratio:.2f}x | Liq +{liq_growth_pct:.1f}%)"
                elif 'S3_US_PEAK' in s_name:
                    if (cfg['pb_min'] <= pullback_pct <= cfg['pb_max']) and price_usd > w['last_price'] and bs_ratio >= cfg['min_bs'] and liq_growth_pct >= 0.0:
                        trigger_buy = True
                        trigger_desc = f"US Pullback -{pullback_pct:.1f}% (B/S {bs_ratio:.2f}x)"

            w['last_bs'] = bs_ratio
            w['last_buys'] = buys_5m
            w['last_price'] = price_usd

            if trigger_buy:
                invest_usd = eng['cash_usd'] * cfg['alloc']
                if invest_usd >= 1.4:
                    eng['cash_usd'] -= invest_usd
                    slip = calc_dynamic_slippage(invest_usd, liq_usd)
                    eff_usd = invest_usd * (1 - slip)
                    tokens_bought = eff_usd / price_usd
                    eng['positions'][pair_addr] = {
                        'token_address': token_addr, 'symbol': symbol,
                        'entry_price': price_usd, 'highest_price': price_usd,
                        'entry_liq': liq_usd, 'entry_time': now_ts,
                        'invested_usd': invest_usd, 'realized_usd': 0.0,
                        'tokens': tokens_bought, 'init_tokens': tokens_bought,
                        'dynamic_sl_pct': cfg['hard_sl'], 'breakeven_locked': False,
                        'tp1_hit': False, 'tp2_hit': False, 'sl_breach_ticks': 0
                    }
                    now_str = datetime.now().strftime('%H:%M:%S')
                    write_log(f"🚀 [{now_str}] [{v_name:<21}] BELI {symbol:<10} (${price_usd:.6f}) | Alokasi: ${invest_usd:.2f} | {trigger_desc}")
                del eng['watchlist'][token_addr]
            continue

        # TAHAP 1: SELEKSI MASUK WATCHLIST
        if not (cfg['min_m5'] <= m5_chg <= cfg['max_m5'] and h1_chg > 0):
            continue

        if (bs_ratio >= cfg['min_bs'] and vol_to_liq >= 0.18 and avg_tx_usd >= cfg['min_avg_tx'] and fdv_to_liq <= cfg['max_fdv_liq'] and buys_5m >= cfg['min_buys']):
            if token_addr not in audit_cache:
                if audits_this_cycle >= 4:
                    continue
                audits_this_cycle += 1

            is_safe, score, _ = verify_contract_safety(token_addr, cfg['max_rug_score'])
            if is_safe:
                eng['watchlist'][token_addr] = {
                    'symbol': symbol, 'init_price': price_usd, 'peak_price': price_usd,
                    'last_price': price_usd, 'init_liq': liq_usd, 'last_bs': bs_ratio,
                    'last_buys': buys_5m, 'added_time': now_ts, 'checks': 0, 'audit_score': score
                }

# ==============================================================================
# 6. CETAK KLASEMEN MATRIKS 8 PARAMETER V5
# ==============================================================================
def print_leaderboard(session_elapsed):
    elapsed_h = (total_elapsed_sec + session_elapsed) / 3600.0
    now_utc = datetime.now(timezone.utc)
    wib_hour = (now_utc.hour + 7) % 24
    now_str = now_utc.strftime('%Y-%m-%d %H:%M:%S UTC') + f" ({wib_hour:02d}:{now_utc.minute:02d} WIB)"
    active_session = get_chronos_base_session(now_utc.hour)['session_name']
    sol_status = f"SOL: ${sol_macro_state['price']:.2f} (m5: {sol_macro_state['m5']:+.1f}%, h1: {sol_macro_state['h1']:+.1f}%)"

    lines = [
        "\n========================================================================================================================",
        f"🏆 MATRIKS PARAMETER V5.0 (4 VORTEX vs 4 CHRONOS) | Durasi: {elapsed_h:.2f} Jam | {now_str}",
        f"🌐 Sesi Aktif: {active_session} | {sol_status}",
        "------------------------------------------------------------------------------------------------------------------------",
        f"{'VARIAN PARAMETER':<22} | {'EKUITAS':<10} | {'ROI (%)':<9} | {'WIN/LOSS':<10} | {'WIN RATE':<9} | {'PROFIT FACTOR':<13} | {'MAX DD':<8} | {'INTAI/AKTIF'}",
        "------------------------------------------------------------------------------------------------------------------------"
    ]
    ranking = []
    for v_name in COMPETITORS:
        eng = engines[v_name]
        tot_eq = get_total_equity(v_name)
        roi = ((tot_eq - INITIAL_BALANCE) / INITIAL_BALANCE) * 100
        tot_t = eng['wins'] + eng['losses']
        wr = (eng['wins'] / tot_t) * 100 if tot_t > 0 else 0.0
        pf = (eng['gross_profit'] / eng['gross_loss']) if eng['gross_loss'] > 0 else (99.9 if eng['gross_profit'] > 0 else 0.0)
        ranking.append((tot_eq, v_name, roi, eng['wins'], eng['losses'], wr, pf, eng['max_dd_pct'], len(eng['watchlist']), len(eng['positions'])))

    ranking.sort(reverse=True, key=lambda x: x[0])
    for eq, v_name, roi, w, l, wr, pf, dd, wl_cnt, act in ranking:
        pf_str = "INF (0 Loss)" if (l == 0 and w > 0) else f"{pf:.2f}x"
        lines.append(f"{v_name:<22} | ${eq:<9.2f} | {roi:+8.1f}% | {w:>3}W/{l:<3}L  | {wr:>7.1f}% | {pf_str:<13} | -{dd:>5.1f}% | {wl_cnt}WL / {act}Pos")
    lines.append("========================================================================================================================\n")
    write_log("\n".join(lines))

def main():
    init_or_load_state()
    session_start = datetime.now(timezone.utc).timestamp()
    write_log("🦅 MATRIX PARAMETER OPTIMIZER V5.0 AKTIF (8 Racikan Parameter Berjalan Paralel)")

    cycle = 0
    while True:
        cycle += 1
        now_ts = datetime.now(timezone.utc).timestamp()
        session_elapsed = now_ts - session_start

        best_pairs, open_pairs = fetch_shared_market_data(cycle)
        for v_name in COMPETITORS:
            process_competitor(v_name, best_pairs, open_pairs)

        if cycle % 10 == 0:
            save_state(session_elapsed, push_to_git=False)

        if cycle % 30 == 0:
            print_leaderboard(session_elapsed)

        if cycle % 150 == 0:
            save_state(session_elapsed, push_to_git=True)

        if session_elapsed >= MAX_RUNTIME_SECONDS:
            print_leaderboard(session_elapsed)
            save_state(session_elapsed, push_to_git=True)
            write_log("🔄 [ESTAFET SESI SEMPURNA] State V5 berhasil di-push ke GitHub!")
            break

        time.sleep(6)

if __name__ == '__main__':
    main()
