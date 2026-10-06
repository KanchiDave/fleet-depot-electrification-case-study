"""Fleet depot electrification: reproduces every number in README.md and redraws the charts.

Run:  python3 model.py
No third-party packages needed.
"""
import math
import os

# ---------------------------------------------------------------- inputs
# Vehicle and fuel
SEMI_KWH_PER_MILE = 1.55        # Tesla Semi, ArcBest pilot
ELEC_PRICE = 0.30               # $/kWh, California example
DIESEL_PRICE = 6.00             # $/gallon
SEMI_DIESEL_MPG = 8

# Depot (Amazon Seattle example, E&E News) plus course assumptions
STATIONS = 70
STATION_KW = 10.5
LINE_LOSS_KW = 0.5              # per station, between meter and charger
VANS = 100
MILES_PER_VAN_DAY = 80
VAN_KWH_PER_MILE = 0.9
DAYS = 30
LOCKOUT_HOURS = 5               # chargers off 4pm to 9pm
VAN_DIESEL_MPG = 12
INFRA_MONTHLY = 50_000          # amortised capital and upkeep on a $5M site

# Puget Sound Energy Schedule 558, energy and demand option
BASIC_CHARGE = 4413.33          # $/month
DEMAND_CHARGE = 1.53            # $/kW-month, off-peak
ENERGY_CHARGE = 0.02795         # $/kWh, off-peak

# Capacity value
PJM_CAP = 555                   # $/MW-day, backstop auction price cap
VOLTUS_MW = 100
HOME_BATTERY_KWH = 39.2
HOME_BATTERY_COST_PER_KWH = 400
HOME_BATTERY_HOURS = 7
LYRIQ_KW = 10

# Carbon
HI_LB_PER_KWH = 1.2991624590     # EIA 2024, Hawaii electric power CO2 / net generation
WA_LB_PER_KWH = 0.2223205556     # EIA 2024, Washington
LB_PER_GAL_GAS, LB_PER_GAL_DIESEL, LB_PER_TONNE = 20, 22, 2204
ANNUAL_MILES = 15_000

# Clean fuel credits
CI_GASOLINE_2026 = 75.16        # gCO2e/MJ, CARB LCFS benchmark
EER_LD_BEV = 3.4
CI_ELECTRICITY = 0              # assumes 100% renewable supply
MJ_PER_KWH = 3.6
CA_CREDIT = 77.00               # $/tonne, August 2026 average
WA_CREDIT = 45.47               # $/tonne, Q2 2026

# ---------------------------------------------------------------- model
def three_phase_kw(volts, amps):
    return volts * amps * math.sqrt(3) / 1000

r = {}
# 1. fuel cost per mile, Class 8
r["semi_elec_per_mile"] = SEMI_KWH_PER_MILE * ELEC_PRICE
r["semi_diesel_per_mile"] = DIESEL_PRICE / SEMI_DIESEL_MPG

# 2. what a service can power
r["svc_small_kw"] = 208 * 120 / 1000
r["svc_mid_kw"] = three_phase_kw(480, 200)
r["svc_large_kw"] = three_phase_kw(480, 2000)
r["dcfc_200kw_count"] = r["svc_large_kw"] / 200

# 3. battery-buffered charging on the mid-size service
r["buffer_kwh"] = r["svc_mid_kw"] * 20
r["buffer_out_kw"] = r["buffer_kwh"] * 0.90 * 0.85 / 4      # keep 10% in reserve, 85% efficient
r["buffer_delivered_kwh"] = r["buffer_out_kw"] * 4
r["semi_range_miles"] = r["buffer_delivered_kwh"] / 6 / SEMI_KWH_PER_MILE

# 4. depot energy, demand and bill
r["kwh_to_vans"] = VANS * MILES_PER_VAN_DAY * VAN_KWH_PER_MILE * DAYS
r["kwh_purchased"] = r["kwh_to_vans"] * (1 + LINE_LOSS_KW / STATION_KW)
r["peak_kw"] = STATIONS * (STATION_KW + LINE_LOSS_KW)
r["load_factor"] = r["kwh_purchased"] / (r["peak_kw"] * 24 * DAYS)
r["charger_utilisation"] = (r["kwh_to_vans"] / DAYS) / (STATIONS * STATION_KW * (24 - LOCKOUT_HOURS))
r["flat_kw"] = r["kwh_purchased"] / DAYS / (24 - LOCKOUT_HOURS)   # same energy, spread evenly
r["bill_demand"] = r["peak_kw"] * DEMAND_CHARGE
r["bill_energy"] = r["kwh_purchased"] * ENERGY_CHARGE
r["bill"] = BASIC_CHARGE + r["bill_demand"] + r["bill_energy"]
r["fleet_miles"] = VANS * MILES_PER_VAN_DAY * DAYS
r["diesel_cost"] = r["fleet_miles"] / VAN_DIESEL_MPG * DIESEL_PRICE
r["electric_all_in"] = r["bill"] + INFRA_MONTHLY

# 5. capacity value
r["cap_per_kw_year"] = PJM_CAP / 1000 * 365
r["voltus_year"] = PJM_CAP * VOLTUS_MW * 365
r["home_kw"] = HOME_BATTERY_KWH / HOME_BATTERY_HOURS
r["home_cost"] = HOME_BATTERY_KWH * HOME_BATTERY_COST_PER_KWH
r["home_rev_year"] = r["home_kw"] * r["cap_per_kw_year"]
r["home_payback_years"] = r["home_cost"] / r["home_rev_year"]
r["lyriq_rev_year"] = LYRIQ_KW * r["cap_per_kw_year"]
r["unmanaged_mw"] = 1_000_000 * 10 / 1000

# 6. carbon
r["hi_ev_lb"] = ANNUAL_MILES / 4 * HI_LB_PER_KWH
r["hi_gas_lb"] = ANNUAL_MILES / 25 * LB_PER_GAL_GAS
r["wa_van_lb"] = ANNUAL_MILES / 2 * WA_LB_PER_KWH
r["wa_diesel_lb"] = ANNUAL_MILES / 11 * LB_PER_GAL_DIESEL
r["payback_miles"] = 4 * LB_PER_TONNE / (LB_PER_GAL_GAS / 25 - HI_LB_PER_KWH / 4)

# 7. clean fuel credits
r["tonnes_per_kwh"] = (CI_GASOLINE_2026 * EER_LD_BEV - CI_ELECTRICITY) * 1e-6 * MJ_PER_KWH
r["ca_credit_per_kwh"] = r["tonnes_per_kwh"] * CA_CREDIT
r["wa_credit_month"] = r["tonnes_per_kwh"] * r["kwh_to_vans"] * WA_CREDIT
r["electric_net"] = r["electric_all_in"] - r["wa_credit_month"]

# ---------------------------------------------------------------- charts
SURFACE, INK, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
FONT = "font-family='-apple-system,Segoe UI,Helvetica,Arial,sans-serif'"

def bar(x, y, w, h, fill, round_end=True):
    """Horizontal bar, square at the baseline, 4px rounded at the data end."""
    if not round_end or w < 8:
        return f"<rect x='{x:.1f}' y='{y}' width='{w:.1f}' height='{h}' fill='{fill}'/>"
    e = x + w
    return (f"<path d='M{x:.1f},{y} H{e-4:.1f} Q{e:.1f},{y} {e:.1f},{y+4} V{y+h-4} "
            f"Q{e:.1f},{y+h} {e-4:.1f},{y+h} H{x:.1f} Z' fill='{fill}'/>")

def frame(width, height, title, subtitle, body):
    return (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {width} {height}' width='{width}' "
            f"height='{height}' role='img' aria-label='{title}' {FONT}>"
            f"<rect width='{width}' height='{height}' fill='{SURFACE}'/>"
            f"<text x='24' y='34' font-size='17' font-weight='600' fill='{INK}'>{title}</text>"
            f"<text x='24' y='56' font-size='13' fill='{MUTED}'>{subtitle}</text>{body}</svg>")

def cost_chart():
    rows = [("Diesel fleet", [(r["diesel_cost"], AQUA)]),
            ("Electric, utility bill only", [(r["bill"], BLUE)]),
            ("Electric, with charging site", [(r["bill"], BLUE), (INFRA_MONTHLY, ORANGE)])]
    x0, plot_w, top, step, h = 210, 420, 118, 50, 22
    scale = plot_w / 120_000
    out = []
    for i, (name, colour) in enumerate([("Diesel fuel", AQUA), ("Utility bill", BLUE),
                                        ("Charging site capital and upkeep", ORANGE)]):
        lx = 24 + [0, 110, 215][i]
        out.append(f"<rect x='{lx}' y='76' width='10' height='10' rx='2' fill='{colour}'/>"
                   f"<text x='{lx+16}' y='85' font-size='12' fill='{MUTED}'>{name}</text>")
    for t in range(0, 120_001, 40_000):
        gx = x0 + t * scale
        out.append(f"<line x1='{gx}' y1='{top-12}' x2='{gx}' y2='{top+step*3-14}' stroke='{GRID}'/>"
                   f"<text x='{gx}' y='{top+step*3+4}' font-size='11' fill='{MUTED}' text-anchor='middle'>"
                   f"{'$0' if t == 0 else f'${t//1000}k'}</text>")
    for i, (label, segs) in enumerate(rows):
        y, x = top + i * step, x0
        out.append(f"<text x='{x0-12}' y='{y+15}' font-size='13' fill='{INK}' text-anchor='end'>{label}</text>")
        for j, (v, colour) in enumerate(segs):
            w = v * scale
            out.append(bar(x, y, w - (0 if j == len(segs) - 1 else 2), h, colour, j == len(segs) - 1))
            x += w
        total = sum(v for v, _ in segs)
        out.append(f"<text x='{x+8}' y='{y+15}' font-size='13' font-weight='600' fill='{INK}'>${total:,.0f}</text>")
    return frame(720, 290, "Monthly fueling cost, 100 delivery vans",
                 "240,000 fleet miles a month. Diesel at $6.00 a gallon and 12 mpg.", "".join(out))

def capacity_chart():
    rows = [("208 V single-phase, 120 A", r["svc_small_kw"], "Level 2 AC"),
            ("480 V three-phase, 200 A", r["svc_mid_kw"], "one DC fast charger"),
            ("Same 200 A service + battery", r["buffer_out_kw"], "for 4 hours a day"),
            ("480 V three-phase, 2,000 A", r["svc_large_kw"], "eight 200 kW chargers")]
    x0, plot_w, top, step, h = 230, 240, 92, 46, 22
    scale = plot_w / 1800
    out = []
    for t in range(0, 1801, 600):
        gx = x0 + t * scale
        out.append(f"<line x1='{gx}' y1='{top-12}' x2='{gx}' y2='{top+step*4-14}' stroke='{GRID}'/>"
                   f"<text x='{gx}' y='{top+step*4+4}' font-size='11' fill='{MUTED}' text-anchor='middle'>"
                   f"{t:,} kW</text>")
    for i, (label, v, note) in enumerate(rows):
        y, w = top + i * step, v * scale
        out.append(f"<text x='{x0-12}' y='{y+15}' font-size='13' fill='{INK}' text-anchor='end'>{label}</text>"
                   + bar(x0, y, w, h, BLUE) +
                   f"<text x='{x0+w+8}' y='{y+15}' font-size='13' fill='{INK}'>"
                   f"<tspan font-weight='600'>{v:,.0f} kW</tspan><tspan fill='{MUTED}'>  {note}</tspan></text>")
    return frame(720, 300, "Charging power available by electrical service",
                 "A battery lets a 200 A service dispense almost four times its own rating.", "".join(out))

if __name__ == "__main__":
    for k, v in r.items():
        print(f"{k:24s} {v:,.4f}")
    here = os.path.dirname(os.path.abspath(__file__))
    for name, svg in (("monthly-cost.svg", cost_chart()), ("service-capacity.svg", capacity_chart())):
        with open(os.path.join(here, "charts", name), "w") as f:
            f.write(svg)
