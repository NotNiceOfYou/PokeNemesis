from nemesis import Nemesis

DB_CONFIG = {
    'dbname': 'PokemonDatabase',
    'user': 'postgres',
    'password': 'abcd1234',
    'host': 'localhost',
    'port': '5432'
}

# Initialize the nemesis engine (GA version)
nemesis = Nemesis(DB_CONFIG)

# Define different opponent teams
teams_to_test = [
    [1, 2, 3, 4, 5, 6],
    [7, 8, 9, 10, 11, 12],
    [25, 26, 27, 28, 29, 30],
    [150, 151, 152, 153, 154, 155],
]

print("Testing Nemesis responses (GA)...\n")
for i, team in enumerate(teams_to_test, 1):
    print(f"Team {i}: {team}")
    nemesis_team = nemesis.get_team(team)
    print(f"Nemesis  → {nemesis_team}\n")