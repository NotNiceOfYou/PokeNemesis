create table pokemon(
id int primary key,
name varchar(255),
hp int,
atk int,
sp_atk int,
def int,
sp_def int,
speed int,
generation int
);

create table types(
id int primary key,
name varchar(255)
);

create table pokemon_types(
pokemon_id int,
type_id int,
primary key (pokemon_id, type_id),
foreign key (pokemon_id) references pokemon(id),
foreign key (type_id) references types(id)
);

create table type_effectiveness(
id int primary key,
atk_id int,
def_id int,
multiplier float,
foreign key (atk_id) references types(id),
foreign key (def_id) references types(id)
);

create table moves(
id int primary key,
name varchar(255),
type_id int,
power int,
accuracy int,
foreign key (type_id) references types(id)
);

create table pokemon_moves(
pokemon_id int,
move_id int,
level_learned int
);

create table evolutions(
pokemon_id_start int,
pokemon_id_end int,
level_evolved int
foreign key (pokemon_id_start) references pokemon(id),
foreign key (pokemon_id_end) references pokemon(id)
);

create table users (
    id int primary key,
    username varchar(255) unique not null,
    password_hash varchar(255) not null
);

create table teams (
    id int primary key,
    user_id int references users(id) on delete cascade,
    name varchar(255) not null,
    pokemon_ids int[] not null
);