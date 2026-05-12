"""
modules/story_database.py - Base de datos SQLite de elementos narrativos + nombres.
"""

import sqlite3
import random
import json
import os
from datetime import datetime

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(_BASE, "data", "stories.db")


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS stories (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT,
            description TEXT,
            tags        TEXT,
            story_text  TEXT,
            created_at  TEXT,
            uploaded    INTEGER DEFAULT 0,
            video_path  TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS characters (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT UNIQUE,
            age       INTEGER,
            role      TEXT,
            traits    TEXT,
            backstory TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS locations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT UNIQUE,
            description TEXT,
            type        TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS plot_hooks (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            hook     TEXT,
            category TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS first_names (
            id     INTEGER PRIMARY KEY AUTOINCREMENT,
            name   TEXT NOT NULL,
            gender TEXT NOT NULL CHECK(gender IN ('M','F'))
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS last_names (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
    """)

    conn.commit()
    _seed_initial_data(conn)
    _seed_names(conn)
    conn.close()


def _seed_initial_data(conn):
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM characters")
    if c.fetchone()[0] > 0:
        return

    characters = [
        ("Maria Gonzalez", 42, "madre manipuladora",
         "dramatica, victimista, controladora",
         "Vive del drama familiar y pone a sus hijos uno contra el otro"),
        ("Carlos Rodriguez", 45, "esposo infiel",
         "encantador, mentiroso, cobarde",
         "Lleva anios con una doble vida que nadie imagina"),
        ("Ana Perez", 26, "hija mayor",
         "inteligente, trabajadora, demasiado sumisa",
         "Siempre sacrifica todo por la familia y nunca es suficiente"),
        ("Diego Martinez", 29, "novio rechazado por la familia",
         "honesto, trabajador, de origen humilde",
         "La familia lo rechaza por sus origenes, aunque tiene mas exito que todos"),
        ("Patricia Gomez", 55, "suegra metiche",
         "hipocrita, controladora, se presenta como santa",
         "Se muda sin avisar y destruye matrimonios desde adentro"),
        ("Roberto Sanchez", 48, "jefe abusivo",
         "favoritista, codicioso, usa su poder para humillar",
         "Lleva anios saboteando empleados para quedarse con su trabajo"),
        ("Laura Torres", 30, "amiga traicionera",
         "envidiosa, falsa, se aprovecha de la amistad",
         "Se hace pasar por mejor amiga pero actua a espaldas"),
        ("Miguel Herrera", 35, "cunado problematico",
         "vago, celoso, siempre busca conflictos",
         "Vive de los demas y envenena las relaciones familiares"),
        ("Sofia Ramirez", 22, "hermana menor",
         "impulsiva, dramatica, siempre en el centro del escandalo",
         "Sus decisiones afectan a toda la familia sin importarle"),
        ("Eduardo Vega", 50, "padre ausente que regresa",
         "arrepentido, tarde para todo, trae secretos del pasado",
         "Regresa despues de anios queriendo recomponer todo lo que destruyo"),
    ]
    c.executemany(
        "INSERT OR IGNORE INTO characters (name, age, role, traits, backstory) VALUES (?,?,?,?,?)",
        characters,
    )

    locations = [
        ("Casa familiar", "La casa donde toda la familia se reune y explotan los conflictos", "hogar"),
        ("Grupo de WhatsApp familiar", "El campo de batalla moderno donde se ventilan todos los trapos sucios", "digital"),
        ("Oficina corporativa", "Donde el drama laboral se mezcla con el personal", "trabajo"),
        ("Boda o quinceañera", "El evento donde siempre se revelan los secretos mas oscuros", "celebracion"),
        ("Hospital", "Donde las crisis de salud revelan las verdaderas prioridades", "crisis"),
        ("Restaurante caro", "Donde se hacen anuncios bomba y confrontaciones dramaticas", "publico"),
        ("Casa de la suegra", "El territorio enemigo donde nunca hay privacidad ni paz", "hogar"),
        ("Aeropuerto", "Lugar de despedidas, reencuentros inesperados y decisiones definitivas", "transito"),
        ("Juzgado o notaria", "Donde los documentos legales cambian vidas y revelan mentiras", "institucional"),
        ("Red social / Instagram", "Donde los secretos se filtran en fotos y stories que nadie debia ver", "digital"),
    ]
    c.executemany("INSERT OR IGNORE INTO locations (name, description, type) VALUES (?,?,?)", locations)

    plot_hooks = [
        ("La herencia que divide a la familia en dos bandos irreconciliables", "herencia"),
        ("El secreto familiar que llevaba anios oculto se revela en el peor momento posible", "secreto"),
        ("Descubri los mensajes en el telefono de mi pareja y mi vida cambio para siempre", "traicion"),
        ("Mi suegra se mudo a nuestra casa sin avisar y esta destruyendo mi matrimonio", "invasion"),
        ("Le preste dinero a un familiar y ahora dice que fue un regalo", "dinero"),
        ("Mi mejor amiga me robo la idea y se llevo todo el credito", "traicion laboral"),
        ("Me entere que mi jefe llevaba anios saboteandome para quedarse con mis logros", "trabajo"),
        ("Mi hermana salio con el hombre que me rompio el corazon hace anios", "familia"),
        ("Descubri que tengo un medio hermano que nadie menciono jamas", "secreto familiar"),
        ("Mi ex aparecio en la boda de mi hermano con una gran sorpresa", "reencuentro"),
        ("Renuncie en publico despues de anios de humillaciones y no me arrepiento", "trabajo"),
        ("Mi hijo me confeso algo que cambio completamente mi forma de ver la vida", "confesion"),
        ("El testamento de mi abuela lo cambio todo y dejo a todos en shock", "herencia"),
        ("Descubri que mi pareja tenia una segunda familia en otra ciudad", "traicion extrema"),
        ("Me echaron del grupo de WhatsApp familiar y ahi empezo todo", "drama digital"),
        ("La foto que subi a Instagram destruyo anios de mentiras familiares", "redes sociales"),
        ("Mi vecina sabia el secreto de mi esposo antes que yo", "traicion comunitaria"),
        ("El dia que decidi no callarme mas y enfrentar a toda la familia", "empoderamiento"),
    ]
    c.executemany("INSERT OR IGNORE INTO plot_hooks (hook, category) VALUES (?,?)", plot_hooks)
    conn.commit()


def _seed_names(conn):
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM first_names")
    if c.fetchone()[0] > 0:
        return

    male_names = [
        "Santiago", "Mateo", "Sebastian", "Nicolas", "Alejandro",
        "Andres", "Diego", "Camilo", "Felipe", "Julian",
        "Daniel", "David", "Carlos", "Jorge", "Luis",
        "Miguel", "Roberto", "Eduardo", "Fernando", "Ricardo",
        "Arturo", "Gustavo", "Hector", "Ivan", "Jesus",
        "Jose", "Juan", "Manuel", "Mario", "Oscar",
        "Pablo", "Pedro", "Rafael", "Raul", "Sergio",
        "Tomas", "Victor", "Ernesto", "Ignacio", "Rodrigo",
        "Emilio", "Gerardo", "Guillermo", "Horacio", "Lorenzo",
        "Mauricio", "Ramon", "Ruben", "Saul", "Valentin",
        "Adrian", "Agustin", "Alberto", "Alfonso", "Alvaro",
        "Armando", "Bernardo", "Cesar", "Claudio", "Cristian",
        "Dante", "Esteban", "Ezequiel", "Fabian", "Francisco",
        "Gabriel", "German", "Hugo", "Jaime", "Joel",
        "Jonathan", "Leonardo", "Marcelo", "Marco", "Martin",
        "Maximiliano", "Nelson", "Omar", "Orlando", "Oswaldo",
        "Patricio", "Renzo", "Ronald", "Salvador", "Simon",
        "Ulises", "Uriel", "Vladimir", "Walter", "Xavier",
        "Yael", "Zacarias", "Aaron", "Abel", "Abraham",
        "Adan", "Alan", "Alexis", "Alfredo", "Angel",
        "Antonio", "Aurelio", "Axel", "Benito", "Boris",
        "Bruno", "Clemente", "Dario", "Edmundo", "Efrain",
        "Eliseo", "Emanuel", "Enrique", "Eugenio", "Fidel",
        "Genaro", "Gilberto", "Gonzalo", "Gregorio", "Hilario",
        "Isaias", "Ismael", "Israel", "Jacobo", "Jeronimo",
        "Javier", "Joaquin", "Jonas", "Julio", "Leandro",
        "Leonel", "Lucas", "Marcos", "Matias", "Melchor",
        "Moises", "Nestor", "Noe", "Norman", "Octavio",
        "Ovidio", "Pascual", "Porfirio", "Reinaldo", "Rene",
        "Rigoberto", "Rogelio", "Rolando", "Romulo", "Rosendo",
        "Samuel", "Santos", "Serafin", "Silverio", "Silvio",
        "Tadeo", "Timoteo", "Tobias", "Trinidad", "Ubaldo",
        "Valente", "Ventura", "Vicente", "Virgilio", "Wenceslao",
        "Wilfredo", "Wilson", "Zenon", "Amado", "Anselmo",
        "Apolinar", "Aquiles", "Arcadio", "Arnoldo", "Arsenio",
        "Atanasio", "Augusto", "Baldomero", "Basilio", "Bautista",
        "Belisario", "Benigno", "Benjamin", "Candelario", "Casimiro",
        "Celestino", "Cipriano", "Ciro", "Cornelio", "Demetrio",
        "Dionisio", "Domingo", "Eleuterio", "Epifanio", "Eusebio",
        "Faustino", "Federico", "Feliciano", "Fermin", "Florencio",
    ]

    female_names = [
        "Valentina", "Sofia", "Isabella", "Camila", "Valeria",
        "Lucia", "Daniela", "Gabriela", "Sara", "Paula",
        "Ana", "Maria", "Laura", "Andrea", "Carolina",
        "Mariana", "Fernanda", "Natalia", "Alejandra", "Veronica",
        "Adriana", "Alicia", "Beatriz", "Cecilia", "Diana",
        "Elena", "Gloria", "Irene", "Julia", "Karen",
        "Liliana", "Lorena", "Luciana", "Magdalena", "Monica",
        "Nora", "Patricia", "Rosa", "Sandra", "Teresa",
        "Viviana", "Ximena", "Yolanda", "Zoe", "Angela",
        "Catalina", "Claudia", "Cristina", "Esperanza", "Fabiola",
        "Florencia", "Graciela", "Ines", "Jacqueline", "Jessica",
        "Karla", "Leticia", "Lourdes", "Luisa", "Marcela",
        "Miriam", "Norma", "Pilar", "Rocio", "Silvia",
        "Sonia", "Susana", "Vanessa", "Victoria", "Virginia",
        "Wendy", "Yesenia", "Abigail", "Brenda", "Cynthia",
        "Dalia", "Esmeralda", "Estela", "Eugenia", "Eva",
        "Flor", "Guadalupe", "Hilda", "Irma", "Isabel",
        "Josefina", "Juana", "Lilia", "Linda", "Luz",
        "Marisol", "Martha", "Mercedes", "Mirna", "Olga",
        "Perla", "Rebeca", "Regina", "Sarita", "Selena",
        "Soledad", "Tania", "Tomasa", "Wanda", "Yareli",
        "Yadira", "Zoraida", "Amalia", "Amparo", "Araceli",
        "Aurora", "Azucena", "Belen", "Blanca", "Carmen",
        "Celia", "Cinthia", "Clara", "Consuelo", "Corina",
        "Delia", "Dolores", "Edith", "Elvira", "Emilia",
        "Enriqueta", "Esther", "Evangelina", "Fatima", "Felicia",
        "Francisca", "Genoveva", "Georgina", "Herminia", "Hortensia",
        "Idalia", "Ileana", "Imelda", "Isidora", "Ivette",
        "Ivonne", "Jacinta", "Janet", "Jasmine", "Josefa",
        "Judith", "Lena", "Leonor", "Lidia", "Lina",
        "Liseth", "Lizbeth", "Lucero", "Lucrecia", "Lupita",
        "Maite", "Manuela", "Margarita", "Maricela", "Mariela",
        "Marlene", "Mayra", "Micaela", "Milagros", "Minerva",
        "Nadia", "Natividad", "Nidia", "Nilda", "Noelia",
        "Noemi", "Nubia", "Ofelia", "Olimpia", "Paola",
        "Petra", "Raquel", "Remedios", "Renata", "Reyna",
        "Rosalba", "Rosalinda", "Rosario", "Rufina", "Sabrina",
        "Samantha", "Selene", "Serafina", "Socorro", "Solange",
        "Stephanie", "Sulema", "Tatiana", "Trinidad", "Ursula",
        "Violeta", "Xiomara", "Yenifer", "Zaida", "Zulema",
    ]

    last_names = [
        "Garcia", "Rodriguez", "Martinez", "Hernandez", "Lopez",
        "Gonzalez", "Perez", "Sanchez", "Ramirez", "Torres",
        "Flores", "Rivera", "Gomez", "Diaz", "Cruz",
        "Morales", "Reyes", "Gutierrez", "Ortiz", "Vargas",
        "Rojas", "Alvarez", "Romero", "Vasquez", "Castillo",
        "Mendoza", "Ramos", "Nunez", "Moreno", "Jimenez",
        "Aguilar", "Silva", "Espinoza", "Medina", "Herrera",
        "Luna", "Castro", "Salinas", "Figueroa", "Contreras",
        "Fuentes", "Acosta", "Miranda", "Cabrera", "Guerrero",
        "Montes", "Campos", "Velazquez", "Guzman", "Munoz",
        "Ruiz", "Suarez", "Vega", "Cortes", "Blanco",
        "Delgado", "Dominguez", "Sandoval", "Carrillo", "Benitez",
        "Rios", "Molina", "Leon", "Ponce", "Alvarado",
        "Gallegos", "Cervantes", "Navarro", "Ibanez", "Leiva",
        "Paredes", "Lara", "Ochoa", "Rivas", "Villanueva",
        "Cardenas", "Rosales", "Pena", "Zamora", "Ibarra",
        "Palacios", "Serrano", "Marin", "Bustamante", "Chavez",
        "Escobar", "Mejia", "Valencia", "Tapia", "Cisneros",
        "Ayala", "Pacheco", "Vera", "Duarte", "Padilla",
        "Cano", "Bravo", "Orellana", "Arias", "Mena",
        "Mora", "Cuellar", "Villalobos", "Trujillo", "Garza",
        "Orozco", "Beltran", "Pizarro", "Quintero", "Montoya",
        "Coronado", "Zapata", "Mercado", "Bonilla", "Osorio",
        "Quispe", "Mamani", "Condori", "Apaza", "Cayo",
        "Huanca", "Ticona", "Chura", "Lazo", "Pari",
        "Soto", "Palma", "Lagos", "Araya", "Espinosa",
        "Sepulveda", "Valenzuela", "Donoso", "Godoy", "Jara",
        "Leal", "Navarrete", "Poblete", "Quijano", "Riffo",
        "Tagle", "Uribe", "Valdivia", "Acuna", "Alarcon",
        "Andrade", "Baeza", "Cabello", "Cifuentes", "Cornejo",
        "Cuevas", "Davila", "Estrada", "Fonseca", "Galindo",
        "Henriquez", "Hurtado", "Iturra", "Jaramillo", "Landeros",
        "Linares", "Mansilla", "Mardones", "Medel", "Mendez",
        "Montenegro", "Montiel", "Moya", "Naranjo", "Neira",
        "Nieto", "Noguera", "Novoa", "Obando", "Ojeda",
        "Oliva", "Olivares", "Orrego", "Palomino", "Parra",
        "Pinto", "Quevedo", "Quiroga", "Quiroz", "Recabarren",
        "Reinoso", "Renteria", "Restrepo", "Riveros", "Robles",
        "Rodas", "Rondon", "Rosado", "Rubio", "Salamanca",
        "Salcedo", "Salgado", "Segura", "Solano", "Solis",
        "Sotelo", "Tamayo", "Tejada", "Tellez", "Teran",
        "Tirado", "Toledo", "Tovar", "Ugarte", "Urquiza",
        "Valderrama", "Venegas", "Villafuerte", "Villalba", "Villar",
    ]

    c.executemany("INSERT INTO first_names (name, gender) VALUES (?,?)", [(n, "M") for n in male_names])
    c.executemany("INSERT INTO first_names (name, gender) VALUES (?,?)", [(n, "F") for n in female_names])
    c.executemany("INSERT OR IGNORE INTO last_names (name) VALUES (?)", [(n,) for n in last_names])
    conn.commit()


# ── Nombres ──

def get_random_name(gender: str = "M") -> tuple:
    if not os.path.exists(DB_PATH):
        init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    gender_code = "F" if gender.upper().startswith("F") else "M"
    c.execute("SELECT name FROM first_names WHERE gender=? ORDER BY RANDOM() LIMIT 1", (gender_code,))
    row = c.fetchone()
    first = row[0] if row else ("Maria" if gender_code == "F" else "Jose")
    c.execute("SELECT name FROM last_names ORDER BY RANDOM() LIMIT 2")
    rows = c.fetchall()
    conn.close()
    if len(rows) >= 2:
        last = f"{rows[0][0]} {rows[1][0]}"
    elif rows:
        last = rows[0][0]
    else:
        last = "Garcia"
    return first, last


def assign_names_to_characters(characters: list) -> list:
    used_firsts = set()
    result = []
    for char in characters:
        role = char.get("role", "").lower()
        gender_hint = char.get("gender", "")
        if not gender_hint:
            if any(w in role for w in ("madre", "suegra", "hija", "hermana", "abuela",
                                       "esposa", "novia", "mujer", "amiga", "jefa")):
                gender_hint = "F"
            elif any(w in role for w in ("padre", "suegro", "hijo", "hermano", "abuelo",
                                          "esposo", "novio", "jefe", "cunado")):
                gender_hint = "M"
            else:
                gender_hint = random.choice(["M", "F"])
        for _ in range(10):
            first, last = get_random_name(gender_hint)
            if first not in used_firsts:
                break
        used_firsts.add(first)
        char = dict(char)
        char["assigned_name"] = f"{first} {last}"
        result.append(char)
    return result


# ── Consultas ──

def get_story_elements() -> dict:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name, age, role, traits, backstory FROM characters ORDER BY RANDOM() LIMIT 4")
    characters = [{"name": r[0], "age": r[1], "role": r[2], "traits": r[3], "backstory": r[4]} for r in c.fetchall()]
    c.execute("SELECT name, description, type FROM locations ORDER BY RANDOM() LIMIT 2")
    locations = [{"name": r[0], "description": r[1], "type": r[2]} for r in c.fetchall()]
    c.execute("SELECT hook, category FROM plot_hooks ORDER BY RANDOM() LIMIT 3")
    hooks = [{"hook": r[0], "category": r[1]} for r in c.fetchall()]
    conn.close()
    return {"characters": characters, "locations": locations, "hooks": hooks}


def get_recent_story_titles(limit: int = 8) -> list:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT title FROM stories ORDER BY created_at DESC LIMIT ?", (limit,))
    titles = [r[0] for r in c.fetchall()]
    conn.close()
    return titles


def save_story(title, description, tags, story_text, video_path=None) -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO stories (title, description, tags, story_text, created_at, video_path) VALUES (?,?,?,?,?,?)",
        (title, description, tags, story_text, datetime.now().isoformat(), video_path),
    )
    story_id = c.lastrowid
    conn.commit()
    conn.close()
    return story_id


def mark_uploaded(story_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE stories SET uploaded=1 WHERE id=?", (story_id,))
    conn.commit()
    conn.close()
