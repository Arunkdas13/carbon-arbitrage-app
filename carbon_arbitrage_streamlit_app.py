import streamlit as st
import pandas as pd
from scipy.interpolate import interp1d
import io

# For demonstration, we read from a CSV string.
# In a real app, you could replace this with st.file_uploader or a local CSV.
CSV_DATA = """Scenario,Variable,2010,2015,2020,2025,2030,2035,2040,2045,2050,2055,2060,2065,2070,2075,2080,2085,2090,2095,2100
NGFS2_Current Policies,Emissions|CO2,27000,32000,34000,33000,32000,31000,30000,29000,28000,27000,26000,25000,24000,23000,22000,21000,20000,19000,18000
NGFS2_Current Policies,Primary Energy|Coal,100,110,105,100,95,90,85,80,75,70,65,60,55,50,45,40,35,30,25
NGFS2_Net-Zero 2050,Emissions|CO2,27000,32000,34000,30000,26000,22000,18000,14000,10000,8000,6000,4000,3000,2000,1500,1000,500,400,300
NGFS2_Net-Zero 2050,Primary Energy|Coal,100,110,105,95,85,70,60,45,30,25,20,15,10,5,4,3,2,1,0.5
"""

# We'll load the data into a DataFrame
df_ngfs = pd.read_csv(io.StringIO(CSV_DATA))

ngfs_years = list(range(2010, 2101, 5))
full_years = range(2023, 2101)

def calculate_rho(beta: float) -> float:
    """Calculate discount rate rho based on the provided beta."""
    rho_f = 0.0208
    carp = 0.0299
    # Always subtract 1% from carp
    carp -= 0.01
    _lambda = 0.5175273490449868
    tax_rate = 0.15
    rho = _lambda * rho_f * (1 - tax_rate) + (1 - _lambda) * (rho_f + beta * carp)
    return rho

def calculate_discount(rho: float, deltat: float) -> float:
    return (1 + rho) ** -deltat

def EJ2MWh(x: float) -> float:
    """Convert EJ to MWh."""
    joule = x * 1e18
    wh = joule / 3600.0
    return wh / 1e6

def EJ2Mcoal(x: float) -> float:
    """Convert EJ to million tonnes of coal."""
    coal = x * 1e9 / 29.3076
    return coal / 1e6

# We reference IEA's 2022 coal emissions for scaling.
coal_emissions_2022_iea = 15.5

def calculate_emissions_and_production(ngfs_scenario: str, df: pd.DataFrame, user_beta: float) -> dict:
    scenario_df = df[df.Scenario == ngfs_scenario]
    # Emissions data (million tonnes) -> convert to Gt
    emissions_row = scenario_df[scenario_df.Variable == "Emissions|CO2"].iloc[0]
    emissions_values = [emissions_row[str(year)] / 1e3 for year in ngfs_years]

    f_e = interp1d(ngfs_years, emissions_values)
    total_emissions = sum(f_e(y) for y in full_years)
    # Rescale emissions to align with reference year 2022
    total_emissions *= (coal_emissions_2022_iea / f_e(2022))

    # Production data (EJ)
    production_row = scenario_df[scenario_df.Variable == "Primary Energy|Coal"].iloc[0]
    production_values = [production_row[str(year)] for year in ngfs_years]
    f_p = interp1d(ngfs_years, production_values)

    rho = calculate_rho(user_beta)
    production_discounted = sum(
        f_p(y) * calculate_discount(rho, y - 2022) for y in full_years
    )

    return {
        "emissions": total_emissions,  # Gt
        "production_2022": EJ2Mcoal(f_p(2022)),
        "production_discounted": production_discounted,
    }

def calculate_cost_and_benefit(df: pd.DataFrame, user_scc: float, user_lcoe: float, user_beta: float):
    ep_cps = calculate_emissions_and_production("NGFS2_Current Policies", df, user_beta)
    ep_nz2050 = calculate_emissions_and_production("NGFS2_Net-Zero 2050", df, user_beta)

    avoided_emissions = ep_cps["emissions"] - ep_nz2050["emissions"]

    # Discounted difference in EJ
    discounted_production_increase = ep_cps["production_discounted"] - ep_nz2050["production_discounted"]
    discounted_production_increase_mwh = EJ2MWh(discounted_production_increase)

    cost = user_lcoe * discounted_production_increase_mwh
    cost /= 1e12  # trillion dollars

    benefit = avoided_emissions * user_scc / 1e3  # trillion dollars

    return avoided_emissions, cost, benefit, ep_cps["production_2022"]

def main():
    st.title("Carbon Arbitrage Opportunity App")
    st.markdown(""" \
## Introduction               
This Streamlit app calculates the carbon arbitrage opportunity using a simplified model:\

- **Carbon Arbitrage Opportunity** = **Benefit** (Social Cost of Carbon * emissions avoided) - **Cost** (LCOE * difference in discounted production) \

**Caveats**:\
- Simplified discount model (using an unlevered beta) \
- LCOE for wind+solar is assumed constant \
- Only focuses on emissions from coal \"""")

    # Sliders for user-controlled parameters
    user_scc = st.slider("Social Cost of Carbon ($/tCO2)", 0.0, 200.0, 80.0, step=5.0)
    user_lcoe = st.slider("Global LCOE Average ($/MWh)", 0.0, 200.0, 59.25, step=1.0)
    user_beta = st.slider("Beta", 0.0, 2.0, 0.9132710997126332, step=0.01)

    st.header("Calculation")
    avoided_emissions, cost, benefit, coal_prod_2022 = calculate_cost_and_benefit(
        df_ngfs, user_scc, user_lcoe, user_beta
    )
    carbon_arbitrage = benefit - cost

    st.write(f"**Global coal production in 2022:** {coal_prod_2022:.2f} million tonnes")
    st.write(f"**Discounted cost:** {cost:.2f} trillion USD")
    st.write(f"**Total emissions prevented:** {avoided_emissions:.2f} GtCO2")
    st.write(f"**Benefit (SCC * avoided emissions):** {benefit:.2f} trillion USD")
    st.subheader(f"**Carbon Arbitrage Opportunity**: {carbon_arbitrage:.2f} trillion USD")

if __name__ == "__main__":
    main()
