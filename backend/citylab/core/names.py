"""Names and faiths of Kamalnagar's citizens.

Kamalnagar is an Indian city (``kamal`` means lotus, after the pond in its central
park), so its people come from India's many communities. Each community has its own
first names and family names, and a family shares one faith: children take their
parents' faith and a name from it.

The shares below are close to a Maharashtrian city's census figures. They shape who
lives here and which place of worship they visit, and nothing else: faith never
changes how much anyone earns, whether they find work, or (in later stages) how
anyone is policed.
"""

from __future__ import annotations

import numpy as np

CITY_NAME = "Kamalnagar"

# (key, label, share of the population)
RELIGIONS: tuple[tuple[str, str, float], ...] = (
    ("hindu", "Hindu", 0.78),
    ("muslim", "Muslim", 0.12),
    ("buddhist", "Buddhist", 0.04),
    ("jain", "Jain", 0.025),
    ("christian", "Christian", 0.02),
    ("sikh", "Sikh", 0.008),
    ("parsi", "Parsi", 0.002),
    ("none", "No religion", 0.005),
)
RELIGION_LABEL = {k: label for k, label, _ in RELIGIONS}
_KEYS = [k for k, _, _ in RELIGIONS]
_SHARES = np.array([s for _, _, s in RELIGIONS]) / sum(s for _, _, s in RELIGIONS)

FIRST: dict[str, dict[str, tuple[str, ...]]] = {
    "hindu": {
        "F": ("Aarti", "Aditi", "Ananya", "Anjali", "Asha", "Bhakti", "Deepa", "Gauri", "Isha", "Jyoti", "Kavya", "Lakshmi",
              "Madhuri", "Meera", "Neha", "Pooja", "Priya", "Radha", "Rutuja", "Sakshi", "Sanika", "Shreya", "Shruti", "Smita",
              "Sneha", "Sunita", "Swati", "Tanvi", "Vaishnavi", "Vidya"),
        "M": ("Aarav", "Aditya", "Ajay", "Akash", "Amit", "Aniket", "Arjun", "Ashok", "Chetan", "Ganesh", "Hemant", "Kiran",
              "Krishna", "Mahesh", "Manoj", "Nikhil", "Omkar", "Pranav", "Prasad", "Rahul", "Rajesh", "Rohan", "Sachin", "Sagar",
              "Sanjay", "Shivam", "Siddharth", "Suresh", "Tushar", "Vinayak"),
    },
    "muslim": {
        "F": ("Aaliya", "Afreen", "Ayesha", "Fatima", "Hina", "Iqra", "Mariam", "Nazia", "Noor", "Rubina", "Saba", "Sana",
              "Shabana", "Tabassum", "Zainab", "Zoya"),
        "M": ("Aamir", "Abdul", "Arif", "Asif", "Faisal", "Farhan", "Hamza", "Imran", "Irfan", "Javed", "Mohammed", "Mustafa",
              "Nadeem", "Rizwan", "Salim", "Sameer", "Shahid", "Tariq", "Yusuf", "Zaid"),
    },
    "buddhist": {
        "F": ("Anjali", "Asha", "Karuna", "Maya", "Pallavi", "Pragya", "Prerna", "Rupali", "Sanghamitra", "Shital", "Sujata",
              "Vaishali"),
        "M": ("Amol", "Ananda", "Bhimrao", "Prashant", "Rahul", "Rajratna", "Sandeep", "Siddharth", "Sumedh", "Sunil", "Vijay",
              "Yogesh"),
    },
    "jain": {
        "F": ("Anushka", "Bhavna", "Darshana", "Hetal", "Khushi", "Mansi", "Nidhi", "Pinal", "Prachi", "Riddhi", "Siddhi",
              "Trishala"),
        "M": ("Abhay", "Amit", "Deepak", "Hitesh", "Jinesh", "Mahavir", "Nilesh", "Paras", "Rishabh", "Sanket", "Sunil",
              "Vardhan"),
    },
    "christian": {
        "F": ("Anita", "Celine", "Christina", "Elizabeth", "Grace", "Jennifer", "Maria", "Mary", "Natasha", "Priscilla",
              "Rachel", "Rose", "Sarah", "Sharon", "Teresa"),
        "M": ("Anthony", "Benjamin", "Christopher", "Daniel", "David", "Francis", "George", "Ivan", "John", "Joseph",
              "Lawrence", "Mathew", "Paul", "Peter", "Thomas", "Victor"),
    },
    "sikh": {
        "F": ("Amrit", "Gurleen", "Gurpreet", "Harleen", "Harpreet", "Jaspreet", "Kiranjit", "Manpreet", "Navneet",
              "Parminder", "Rupinder", "Simran"),
        "M": ("Amarjeet", "Balwinder", "Gurdeep", "Gurpreet", "Harjeet", "Harpreet", "Jasbir", "Jaspal", "Kuldeep", "Manjeet",
              "Navjot", "Ranjit", "Sukhwinder", "Tejinder"),
    },
    "parsi": {
        "F": ("Anahita", "Delnaz", "Freny", "Havovi", "Perizad", "Roshan", "Shirin", "Zarine"),
        "M": ("Behram", "Cyrus", "Darius", "Farokh", "Jamshed", "Kaizad", "Mehernosh", "Rustom", "Sorab", "Zubin"),
    },
}

FAMILY: dict[str, tuple[str, ...]] = {
    "hindu": ("Patil", "Deshmukh", "Kulkarni", "Joshi", "Pawar", "Jadhav", "Shinde", "Chavan", "More", "Salunkhe", "Deshpande",
              "Gokhale", "Bhosale", "Sawant", "Naik", "Sharma", "Verma", "Gupta", "Iyer", "Nair", "Menon", "Reddy", "Rao", "Bose",
              "Das", "Kapoor", "Malhotra", "Mishra", "Pandey", "Yadav"),
    "muslim": ("Khan", "Shaikh", "Ansari", "Qureshi", "Siddiqui", "Sayyed", "Pathan", "Inamdar", "Mulla", "Tamboli", "Bagwan",
               "Momin", "Hussain", "Ali"),
    "buddhist": ("Kamble", "Bhalerao", "Waghmare", "Gaikwad", "Kharat", "Salve", "Bansode", "Ingle", "Sonawane", "Meshram",
                 "Wankhede"),
    "jain": ("Shah", "Jain", "Mehta", "Oswal", "Gandhi", "Doshi", "Sanghvi", "Lodha", "Bafna", "Chordia", "Kothari", "Munot"),
    "christian": ("D'Souza", "Fernandes", "Pereira", "Rodrigues", "D'Mello", "Gomes", "Lobo", "Pinto", "Thomas", "Mathew",
                  "Kurian", "Varghese"),
    "sikh": ("Gill", "Sandhu", "Grewal", "Bedi", "Ahluwalia", "Sethi", "Chadha", "Bajwa", "Sidhu", "Dhillon", "Bhatia", "Kohli"),
    "parsi": ("Irani", "Wadia", "Mistry", "Bharucha", "Daruwalla", "Engineer", "Contractor", "Batliwala", "Dastur"),
}


def pick_religion(rng: np.random.Generator) -> str:
    return _KEYS[int(rng.choice(len(_KEYS), p=_SHARES))]


def _naming(religion: str, rng: np.random.Generator) -> str:
    """People with no religion were still named by a family from one of the communities."""
    if religion in FIRST:
        return religion
    return _KEYS[int(rng.choice(len(_KEYS) - 1, p=_SHARES[:-1] / _SHARES[:-1].sum()))]


def first_name(rng: np.random.Generator, religion: str, sex: str) -> str:
    given = str(rng.choice(FIRST[_naming(religion, rng)][sex]))
    if religion == "sikh":  # Sikh men are Singh and women Kaur, before the family name
        given += " Singh" if sex == "M" else " Kaur"
    return given


def family_name(rng: np.random.Generator, religion: str) -> str:
    return str(rng.choice(FAMILY[_naming(religion, rng)]))
