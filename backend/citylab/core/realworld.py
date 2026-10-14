"""What a real Indian town of about 2 lakh people looks like, from official surveys.

Kamalnagar's books start from these figures, and the people on the map are tuned to
match them. The figures are rounded national urban averages, not any one town's:

* Census of India 2011 (urban): age structure, sex ratio, household size.
* Sample Registration System (SRS) bulletins 2020-21 (urban): birth and death rates.
* Periodic Labour Force Survey (PLFS) 2023-24 (urban): who works, unemployment, earnings.
* NCRB, Crime in India 2022: thefts and burglaries reported per lakh people.
* BPR&D, Data on Police Organisations 2023: police per lakh people.
* National Medical Commission / health ministry: about one doctor per 1,000 people.
* NSS 75th round (2017-18), health: how often people fall ill and see a doctor.
* World Happiness Report 2024: India's average life evaluation, about 4.1 out of 10.
"""

from __future__ import annotations

TOWN_POPULATION = 200_000  # 2 lakh: the size of a real municipal town

# age bands (years) and their share of an urban Indian population
AGE_BANDS: tuple[tuple[int, int], ...] = ((0, 6), (6, 18), (18, 30), (30, 45), (45, 60), (60, 100))
AGE_LABELS = ("under 6", "6 to 17", "18 to 29", "30 to 44", "45 to 59", "60 and over")
AGE_SHARES = (0.095, 0.195, 0.225, 0.22, 0.155, 0.11)
MALE_SHARE = 1000 / (1000 + 929)  # 929 women for every 1,000 men in towns (Census 2011)
HOUSEHOLD_SIZE = 4.0  # people per household in towns today (NFHS-5, 2019-21)

# life and death, per 1,000 people a year (SRS, urban)
BIRTHS_PER_1000 = 16.0
DEATHS_PER_1000 = 5.6
# chance of dying in a year, by age band: an urban life table, summing to about 5.6 per 1,000
DEATH_RATE_BY_AGE = (0.0045, 0.0005, 0.0011, 0.0021, 0.0065, 0.031)
NET_MIGRATION = 0.013  # towns grow about 2.3% a year: 1% from births, the rest from people moving in
MIGRANT_AGES = (0.10, 0.15, 0.45, 0.22, 0.06, 0.02)

# getting about (NFHS-5, 2019-21, urban households): few have a car, most have a two-wheeler
CAR_OWNERS = 0.13
SCOOTER_OWNERS = 0.6

# work (PLFS 2023-24, urban, usual status)
IN_WORK_FORCE = {  # share of each age band and sex in the labour force: (men, women)
    (18, 30): (0.72, 0.24), (30, 45): (0.97, 0.28), (45, 60): (0.93, 0.25), (60, 100): (0.32, 0.06),
}
UNEMPLOYMENT = 0.051
RETIREMENT_AGE = 60  # most salaried jobs end at 58 to 60; shopkeepers and casual workers carry on
LAST_WORKING_AGE = 70


def work_force_share(age: float, sex: str) -> float:
    """The chance that someone this age and sex works or looks for work (the rest study, keep house or have retired)."""
    for (lo, hi), (men, women) in IN_WORK_FORCE.items():
        if lo <= age < hi:
            return men if sex == "M" else women
    return 0.0
IN_SCHOOL = {(6, 18): 0.93, (18, 30): 0.12}
MONTHLY_EARNINGS = {"regular": 21_000.0, "self-employed": 17_000.0, "casual": 13_000.0}

# crime (NCRB 2022): thefts and burglaries reported, and how many are solved
THEFTS_PER_LAKH = 55.0
REPORTED = 0.3  # assumed: most petty thefts never reach the police, so about 3 in 10 become an FIR
CLEARED = 0.3  # share of reported thefts that end in an arrest

# public services
POLICE_PER_LAKH = 150.0  # actual strength; about 195 posts sanctioned, many unfilled
DOCTORS_PER_1000 = 1.0
PUPILS_PER_TEACHER = 30.0

# health (NSS 75th round, urban): about 9% are ill in any fortnight and most see a doctor
FALL_ILL_PER_DAY = 0.0055
ILL_AT_ANY_TIME = 0.04
DOCTOR_VISITS_PER_DAY = 0.0042

# municipal money: Indian towns raise only part of what they spend; the state passes on
# GST compensation and grants worth about a third of their income (RBI, municipal finances 2022)
STATE_GRANT_PER_PERSON_YEAR = 750.0  # less here, as Kamalnagar also collects sales tax itself

HAPPINESS = 41.0  # out of 100: India's life evaluation of about 4.1 out of 10

__all__ = [name for name in dir() if name.isupper()] + ["work_force_share"]
