import os
import streamlit as st
import pandas as pd
from google import genai

# ----------------------------------------------------------------------------
# API key: NEVER hardcode it. Put it in .streamlit/secrets.toml as
#   GEMINI_API_KEY = "your-key"
# or export it as an environment variable before launching Streamlit.
# ----------------------------------------------------------------------------
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY", ""))

st.set_page_config(
    page_title="Institutional M&A Teaser & Valuation Generator",
    page_icon="⚡",
    layout="wide",
)

st.title("⚡ Institutional M&A Teaser & Valuation Generator")
st.markdown("**Driver-based DCF engine with AI teaser generation** | *For M&A and coverage teams*")
st.divider()

# ============================================================ SIDEBAR
st.sidebar.header("1. Target configuration")
target_name = st.sidebar.text_input("Target company name", value="Delivery Hero SE")

st.sidebar.header("2. Income statement drivers")
rev_latest = st.sidebar.number_input("Latest revenue (€M)", value=14803.4, step=100.0)
revenue_cagr = st.sidebar.number_input("Revenue CAGR, years 1-5 (%)", value=8.0, step=0.5) / 100
ebitda_margin = st.sidebar.number_input("Steady-state Adj. EBITDA margin (%)", value=12.0, step=0.5) / 100
da_pct = st.sidebar.number_input("D&A (% of revenue)", value=3.0, step=0.25) / 100

st.sidebar.header("3. Cash flow and balance sheet drivers")
tax_rate = st.sidebar.number_input("Effective tax rate (%)", value=30.175, step=0.5) / 100
capex_pct = st.sidebar.number_input("CapEx (% of revenue)", value=2.3, step=0.1) / 100
nwc_pct = st.sidebar.number_input("ΔNWC (% of revenue growth)", value=1.5, step=0.5) / 100

st.sidebar.header("4. Valuation and deal parameters")
net_debt = st.sidebar.number_input("Net debt (€M)", value=2512.8, step=50.0)
nci = st.sidebar.number_input("Minority interests (€M)", value=154.2, step=10.0,
                              help="Deducted from enterprise value alongside net debt")
shares_out = st.sidebar.number_input("Diluted shares (M)", value=306.5, step=1.0)
wacc = st.sidebar.number_input("WACC (%)", value=10.0, step=0.25) / 100
g_rate = st.sidebar.number_input("Terminal growth rate g (%)", value=2.0, step=0.25) / 100
offer_price = st.sidebar.number_input("Offer price per share (€)", value=41.50, step=0.50)
mid_year = st.sidebar.checkbox("Mid-year discounting convention", value=True,
                               help="Cash arrives through the year rather than on 31 December")

run_btn = st.sidebar.button("🚀 Run valuation", type="primary")

YEARS = ["2026E", "2027E", "2028E", "2029E", "2030E"]

# ============================================================ ENGINE
if run_btn:
    if wacc <= g_rate:
        st.error("WACC must exceed the terminal growth rate, otherwise the perpetuity is meaningless.")
        st.stop()

    revenues, rev = [], rev_latest
    for _ in range(5):
        rev *= (1 + revenue_cagr)
        revenues.append(rev)

    # margin ramps from 70% to 100% of the steady-state level over the five years
    margins = [ebitda_margin * (0.7 + i * 0.075) for i in range(5)]
    ebitda = [r * m for r, m in zip(revenues, margins)]

    da = [r * da_pct for r in revenues]
    ebit = [e - d for e, d in zip(ebitda, da)]
    taxes = [max(0.0, e * tax_rate) for e in ebit]          # no tax credit on a loss year
    nopat = [e - t for e, t in zip(ebit, taxes)]
    capex = [r * capex_pct for r in revenues]

    delta_nwc = []
    for i in range(5):
        prev = rev_latest if i == 0 else revenues[i - 1]
        delta_nwc.append((revenues[i] - prev) * nwc_pct)

    ufcf = [nopat[i] + da[i] - capex[i] - delta_nwc[i] for i in range(5)]

    offset = 0.5 if mid_year else 1.0
    discount_factors = [1 / ((1 + wacc) ** (i + offset)) for i in range(5)]
    pv_ufcf = [f * d for f, d in zip(ufcf, discount_factors)]

    terminal_value = ufcf[-1] * (1 + g_rate) / (wacc - g_rate)
    pv_terminal_value = terminal_value * discount_factors[-1]

    enterprise_value = sum(pv_ufcf) + pv_terminal_value
    equity_value = enterprise_value - net_debt - nci
    fair_value_per_share = equity_value / shares_out
    premium = (offer_price - fair_value_per_share) / fair_value_per_share * 100

    # store EVERYTHING used, so the table can never drift from the headline metrics
    st.session_state["res"] = dict(
        target_name=target_name, rev_latest=rev_latest,
        revenue_cagr=revenue_cagr * 100, ebitda_margin=ebitda_margin * 100,
        revenues=revenues, ebitda=ebitda, da=da, ebit=ebit, taxes=taxes,
        nopat=nopat, capex=capex, delta_nwc=delta_nwc, ufcf=ufcf, pv_ufcf=pv_ufcf,
        enterprise_value=enterprise_value, equity_value=equity_value,
        pv_explicit=sum(pv_ufcf), pv_terminal=pv_terminal_value,
        fair_value_per_share=fair_value_per_share, offer_price=offer_price,
        premium=premium, net_debt=net_debt, nci=nci, wacc=wacc * 100,
        g_rate=g_rate * 100, mid_year=mid_year,
    )

# ============================================================ OUTPUT
if "res" not in st.session_state:
    st.info("👈 Set the drivers in the sidebar and click **Run valuation**.")
    st.stop()

res = st.session_state["res"]

st.subheader(f"📌 Valuation results: **{res['target_name']}**")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Enterprise value (€M)", f"€{res['enterprise_value']:,.1f}")
c2.metric("Equity value (€M)", f"€{res['equity_value']:,.1f}")
c3.metric("DCF implied share price", f"€{res['fair_value_per_share']:.2f}")
c4.metric("Offer price", f"€{res['offer_price']:,.2f}", delta=f"{res['premium']:.1f}% premium")

st.caption(
    f"WACC {res['wacc']:.2f}% · terminal growth {res['g_rate']:.2f}% · "
    f"{'mid-year' if res['mid_year'] else 'end-year'} discounting · "
    f"terminal value is {res['pv_terminal'] / res['enterprise_value']:.0%} of enterprise value"
)

st.divider()
st.subheader("📊 Five-year model and cash flow bridge (€M)")

# built from stored values with a loop: no duplication, no drift
rows = [
    ("Revenue",               res["revenues"]),
    ("Adj. EBITDA",           res["ebitda"]),
    ("(-) D&A",               [-x for x in res["da"]]),
    ("EBIT",                  res["ebit"]),
    ("(-) Taxes",             [-x for x in res["taxes"]]),
    ("NOPAT",                 res["nopat"]),
    ("(+) D&A",               res["da"]),
    ("(-) CapEx",             [-x for x in res["capex"]]),
    ("(-) ΔNWC",              [-x for x in res["delta_nwc"]]),
    ("Unlevered FCF",         res["ufcf"]),
    ("PV of UFCF",            res["pv_ufcf"]),
]
df = pd.DataFrame({"Financial metric (€M)": [r[0] for r in rows]})
for i, y in enumerate(YEARS):
    df[y] = [r[1][i] for r in rows]

st.dataframe(
    df.style.format({y: "{:,.1f}" for y in YEARS}),
    use_container_width=True, hide_index=True,
)

with st.expander("Enterprise value bridge"):
    bridge = pd.DataFrame({
        "Line": ["PV of explicit UFCF", "PV of terminal value", "Enterprise value",
                 "(-) Net debt", "(-) Minority interests", "Equity value",
                 "Diluted shares (M)", "Value per share (€)"],
        "Value": [res["pv_explicit"], res["pv_terminal"], res["enterprise_value"],
                  -res["net_debt"], -res["nci"], res["equity_value"],
                  shares_out, res["fair_value_per_share"]],
    })
    st.dataframe(bridge.style.format({"Value": "{:,.2f}"}),
                 use_container_width=True, hide_index=True)

st.divider()
st.subheader("🤖 AI-generated M&A teaser")

if not GEMINI_API_KEY:
    st.warning("No API key found. Add GEMINI_API_KEY to .streamlit/secrets.toml to enable generation.")

if st.button("✨ Generate teaser", type="secondary", disabled=not GEMINI_API_KEY):
    prompt = f"""You are a sector analyst writing the investment case for {res['target_name']}
for an internal M&A committee. Write in flowing prose, not bullet points, and not under
numbered headings. Four or five paragraphs.

The reader already knows what the company does. What they want from you is a point of view
on whether the price is right, and what would have to be true for it to be right.

Build the argument in this order, but do not label the sections:
- open with the tension between what the business is worth on its own and what is being paid
- explain what drives the valuation: where the growth comes from and where the margin comes from
- state plainly what the premium implies the buyer must believe
- close on the single assumption that, if wrong, breaks the case

The numbers you may use, and only these:
revenue of EUR {res['rev_latest']:,.0f}m growing at {res['revenue_cagr']:.1f}% a year toward an
EBITDA margin of {res['ebitda_margin']:.1f}%; enterprise value EUR {res['enterprise_value']:,.0f}m,
of which {res['pv_terminal']/res['enterprise_value']:.0%} is terminal value; equity value
EUR {res['equity_value']:,.0f}m after net debt of EUR {res['net_debt']:,.0f}m; a DCF value of
EUR {res['fair_value_per_share']:.2f} against an offer of EUR {res['offer_price']:.2f}, a
{res['premium']:.1f}% premium; discounted at {res['wacc']:.2f}% with {res['g_rate']:.2f}% terminal growth.

Rules. Invent nothing: no synergies, no market shares, no competitors, no strategic rationale
that does not follow from the figures above. Never write "compelling", "robust", "rigorous",
"strategic positioning" or "value creation". If a claim is not supported by a number you were
given, leave it out. Short sentences. State things, do not decorate them."""

    with st.spinner("Generating…"):
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(
                model="gemini-3.8-flash", contents=prompt
            )
            st.success("Teaser generated.")
            st.markdown(response.text)
        except Exception as e:
            st.error(f"API call failed: {type(e).__name__} — {e}")
            st.warning(
                "**The text below is a static template, not AI-generated.** "
                "It is filled with the model's own figures."
            )
            st.markdown(f"""
### 1. Executive summary
{res['target_name']} is modelled on a driver-based unlevered DCF over a five-year explicit
forecast, with revenue growing at a {res['revenue_cagr']:.1f}% CAGR toward a steady-state
adjusted EBITDA margin of {res['ebitda_margin']:.1f}%. The offer of €{res['offer_price']:.2f} per
share represents a {res['premium']:.1f}% premium to the DCF implied value of
€{res['fair_value_per_share']:.2f}.

### 2. Model outputs
- Latest reported revenue of €{res['rev_latest']:,.1f}m is the forecast base.
- Enterprise value of €{res['enterprise_value']:,.1f}m, of which
  {res['pv_terminal'] / res['enterprise_value']:.0%} is terminal value.
- Equity value of €{res['equity_value']:,.1f}m after deducting net debt of
  €{res['net_debt']:,.1f}m and minority interests of €{res['nci']:,.1f}m.

### 3. Valuation rationale
Terminal value is calculated on the Gordon growth method at {res['g_rate']:.2f}% and discounted at
a WACC of {res['wacc']:.2f}%, on a {'mid-year' if res['mid_year'] else 'end-year'} convention.
No synergy, accretion or transaction-risk analysis is included in these figures.
""")
