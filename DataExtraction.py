import requests
import psycopg2
import time
import urllib3
from tqdm import tqdm

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

def connect_db():
    conn = psycopg2.connect(
        dbname="PokemonDatabase",
        user="postgres",
        password="abcd1234",
        host="localhost",
        port="5432"
    )
    return conn, conn.cursor()

def load_types_and_effectiveness(cur):
    print("Fetching type data...")
    type_list_resp = requests.get("https://pokeapi.co/api/v2/type/", headers=HEADERS, verify=False)
    type_list_resp.raise_for_status()
    type_results = type_list_resp.json()["results"]

    types_data = []
    for t in tqdm(type_results, desc="Loading type details"):
        detail = requests.get(t["url"], headers=HEADERS, verify=False).json()
        types_data.append({
            "id": detail["id"],
            "name": detail["name"],
            "damage_relations": detail["damage_relations"]
        })

    print("Inserting types into database...")
    for t in types_data:
        cur.execute("INSERT INTO types (id, name) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING",
                    (t["id"], t["name"]))
    cur.connection.commit()

    print("Inserting type effectiveness...")
    cur.execute("SELECT COALESCE(MAX(id), 0) FROM type_effectiveness")
    next_eff_id = cur.fetchone()[0] + 1

    for t in types_data:
        atk_id = t["id"]
        dr = t["damage_relations"]

        for rel in dr["double_damage_to"]:
            def_id = int(rel["url"].split("/")[-2])
            cur.execute("""
                INSERT INTO type_effectiveness (id, atk_id, def_id, multiplier)
                VALUES (%s, %s, %s, 2.0) ON CONFLICT (id) DO NOTHING
            """, (next_eff_id, atk_id, def_id))
            next_eff_id += 1

        for rel in dr["half_damage_to"]:
            def_id = int(rel["url"].split("/")[-2])
            cur.execute("""
                INSERT INTO type_effectiveness (id, atk_id, def_id, multiplier)
                VALUES (%s, %s, %s, 0.5) ON CONFLICT (id) DO NOTHING
            """, (next_eff_id, atk_id, def_id))
            next_eff_id += 1

        for rel in dr["no_damage_to"]:
            def_id = int(rel["url"].split("/")[-2])
            cur.execute("""
                INSERT INTO type_effectiveness (id, atk_id, def_id, multiplier)
                VALUES (%s, %s, %s, 0.0) ON CONFLICT (id) DO NOTHING
            """, (next_eff_id, atk_id, def_id))
            next_eff_id += 1

    cur.connection.commit()

def load_moves(cur):
    print("Loading moves...")
    for i in tqdm(range(1, 201)):
        move_resp = requests.get(f"https://pokeapi.co/api/v2/move/{i}/", headers=HEADERS, verify=False)
        if move_resp.status_code != 200:
            continue
        move = move_resp.json()
        type_id = int(move["type"]["url"].split("/")[-2])
        cur.execute("""
            INSERT INTO moves (id, name, type_id, power, accuracy)
            VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING
        """, (i, move["name"], type_id, move.get("power") or 0, move.get("accuracy") or 100))
    cur.connection.commit()

def load_pokemon(cur):
    print("Loading Pokemon...")
    # Get total number of Pokemon
    count_resp = requests.get("https://pokeapi.co/api/v2/pokemon", headers=HEADERS, verify=False)
    total_pokemon = count_resp.json()["count"]
    print(f"Total Pokemon to load: {total_pokemon}")

    for i in tqdm(range(1, total_pokemon + 1)):
        poke_resp = requests.get(f"https://pokeapi.co/api/v2/pokemon/{i}/", headers=HEADERS, verify=False)
        if poke_resp.status_code != 200:
            continue
        poke = poke_resp.json()
        stats = {s["stat"]["name"]: s["base_stat"] for s in poke["stats"]}

        # Fetch species data to get generation
        species_url = poke["species"]["url"]
        species_resp = requests.get(species_url, headers=HEADERS, verify=False)
        if species_resp.status_code != 200:
            generation = None
        else:
            species_data = species_resp.json()
            # generation is an object with a "name" like "generation-i"
            gen_name = species_data["generation"]["name"]
            # Extract the roman numeral and convert to integer
            generation = int(gen_name.split("-")[-1].replace("i", "1").replace("ii", "2").replace("iii", "3")
                            .replace("iv", "4").replace("v", "5").replace("vi", "6").replace("vii", "7")
                            .replace("viii", "8").replace("ix", "9"))

        cur.execute("""
            INSERT INTO pokemon (id, name, hp, atk, def, sp_atk, sp_def, speed, generation)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING
        """, (
            i, poke["name"],
            stats["hp"], stats["attack"], stats["defense"],
            stats["special-attack"], stats["special-defense"], stats["speed"],
            generation
        ))

        for t in poke["types"]:
            type_id = int(t["type"]["url"].split("/")[-2])
            cur.execute("""
                INSERT INTO pokemon_types (pokemon_id, type_id)
                VALUES (%s, %s) ON CONFLICT (pokemon_id, type_id) DO NOTHING
            """, (i, type_id))

        for move_entry in poke["moves"]:
            move_id = int(move_entry["move"]["url"].split("/")[-2])
            for version in move_entry["version_group_details"]:
                if version["version_group"]["name"] == "firered-leafgreen":
                    cur.execute("""
                        INSERT INTO pokemon_moves (pokemon_id, move_id, level_learned)
                        VALUES (%s, %s, %s)
                    """, (i, move_id, version["level_learned_at"]))

        cur.connection.commit()
        time.sleep(0.05)

def extract_evolution_links(chain_link, start_id=None):
    current_species = chain_link['species']
    current_id = int(current_species['url'].split('/')[-2])

    if start_id is not None:
        level = 40  # default for non‑level evolutions
        for detail in chain_link.get('evolution_details', []):
            if detail.get('trigger', {}).get('name') == 'level-up' and detail.get('min_level') is not None:
                level = detail['min_level']
                break
        yield (start_id, current_id, level)

    for next_link in chain_link.get('evolves_to', []):
        yield from extract_evolution_links(next_link, current_id)

def load_evolutions(cur):
    print("Loading evolutions...")
    # Get total number of Pokemon species
    count_resp = requests.get("https://pokeapi.co/api/v2/pokemon-species", headers=HEADERS, verify=False)
    total_species = count_resp.json()["count"]
    print(f"Total species to process: {total_species}")

    for species_id in tqdm(range(1, total_species + 1)):
        species_url = f"https://pokeapi.co/api/v2/pokemon-species/{species_id}/"
        resp = requests.get(species_url, headers=HEADERS, verify=False)
        if resp.status_code != 200:
            continue
        species_data = resp.json()
        evo_chain_url = species_data.get('evolution_chain', {}).get('url')
        if not evo_chain_url:
            continue
        chain_resp = requests.get(evo_chain_url, headers=HEADERS, verify=False)
        if chain_resp.status_code != 200:
            continue
        chain_data = chain_resp.json()

        for start_id, end_id, level in extract_evolution_links(chain_data['chain']):
            try:
                cur.execute("""
                    INSERT INTO evolutions (pokemon_id_start, pokemon_id_end, level_evolved)
                    VALUES (%s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, (start_id, end_id, level))
            except Exception as e:
                print(f"Skipping ({start_id}, {end_id}, {level}) due to error:", e)
                continue

        cur.connection.commit()
        time.sleep(0.05)

def main():
    conn, cur = connect_db()
    try:
        #load_types_and_effectiveness(cur)
        #load_moves(cur)
        #load_pokemon(cur)
        load_evolutions(cur)
        print("All data loaded successfully.")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    main()