
import requests
from typing import List, Dict
from jsonpath2.path import Path
from datetime import date, timedelta

BOOKING_URL= f'https://www.nightjet.com/nj-booking-ocp'


class Station:

    meta: bool
    name: str
    eva_number: int

    @staticmethod
    def from_json_array(station_json: Dict):
        meta_stations = [Station(int(s['number']), s['meta'], True) for s in station_json if len(s['meta']) > 0]
        if len(meta_stations) == 1:
            return meta_stations[0]
        elif len(meta_stations) > 1:
            raise ValueError(f'Multiple meta station matches, please specify according to: {station_json}')

        stations = [Station.from_json(s) for s in station_json if len(s['meta']) == 0]
        if len(stations) == 1:
            return stations[0]
        elif len(stations) > 1:
            raise ValueError(f'Multiple station matches, please specify according to: {station_json}')

        raise ValueError(f'No matching station found')

    @staticmethod
    def from_json(station_json: Dict):
        return Station(int(station_json['number']), station_json['name'])

    def __init__(self, eva_number: int, name: str, meta: bool = False):
        self.meta = meta
        self.eva_number = eva_number
        self.name = name

    def __str__(self):
        return f'{self.name}{" Area" if self.meta else ""} ({str(self.eva_number)})'


class Train:

    ident: str
    departure: str
    departure_stamp: int
    arrival: str

    @staticmethod
    def from_json(train_json: Dict):
        return Train(
            train_json['train'],
            train_json['departure']['local'],
            int(train_json['departure']['utc']),
            train_json['arrival']['local'])

    def __init__(self, ident: str, departure: str, departure_stamp: int, arrival: str):
        self.ident = ident
        self.departure = departure
        self.departure_stamp = departure_stamp
        self.arrival = arrival

    def __str__(self):
        return f'{self.ident} ({self.departure} - {self.arrival})'


class Connection:

    from_station: Station
    to_station: Station
    trains: List[Train]

    @staticmethod
    def from_json(connection_json: Dict):
        return Connection(
            Station.from_json(connection_json['from']),
            Station.from_json(connection_json['to']),
            [Train.from_json(t) for t in connection_json['trains']])

    def __init__(self, from_station: Station, to_station: Station, trains: List[Train]):
        self.from_station = from_station
        self.to_station = to_station
        self.trains = trains

    def __str__(self):
        return f'{self.from_station} -> {self.to_station}: {", ".join([str(t) for t in self.trains])}'

    def get_departure_train(self):
        if not self.trains:
            raise ValueError('No trains to retrieve departure time from')

        return self.trains[0]


class Offer:

    offers_path = Path.parse_str('$..offers[*]')
    compartments_path = Path.parse_str('$..compartments[*].name.de')
    name: str
    details: List[str]

    @staticmethod
    def from_json(offer_json: str):
        offers = [x.current_value for x in Offer.offers_path.match(offer_json)]
        return [Offer(o['name'], [c.current_value for c in Offer.compartments_path.match(o)]) for o in offers]

    def __init__(self, name: str, details: List[str]):
        self.name = name
        self.details = details

    def __str__(self):
        return f'{self.name}: ({", ".join(self.details)})'


class Traveler:

    gender: str
    year_of_birth: int

    @staticmethod
    def female(year_of_birth: int):
        return Traveler('female', year_of_birth)

    @staticmethod
    def male(year_of_birth: int):
        return Traveler('male', year_of_birth)

    def __init__(self, gender: str, year_of_birth: int):
        self.gender = gender
        self.year_of_birth = year_of_birth


class Nightjet:

    default_header: Dict
    default_body: Dict
    from_station: Station
    to_station: Station
    travelers: List[Traveler]

    def __init__(self, from_station: str, to_station: str, travelers: List[Traveler] = []):
        self.default_body = {
            'lang': 'de'
        }
        start_response = requests.post(f'{BOOKING_URL}/init/start', json=self.default_body).json()
        self.default_header = {
            'X-Token': start_response['token'],
            'Content-Type': 'application/json; charset=utf-8'
        }
        self.from_station = Station.from_json_array(
            requests.get(f'{BOOKING_URL}/stations/find', params=self.default_body | {'name': from_station}).json())
        self.to_station = Station.from_json_array(
            requests.get(f'{BOOKING_URL}/stations/find', params=self.default_body | {'name': to_station}).json())
        self.travelers = [Traveler.male(1980)] if not travelers else travelers

    def list_offers(self, reverse_direction: bool, date: str, results: int = 3):
        fs = self.to_station if reverse_direction else self.from_station
        ts = self.from_station if reverse_direction else self.to_station

        print(f'{fs} -> {ts} {"return" if reverse_direction else "outward"} connections up from {date}:')

        connections = []
        while len(connections) < results:
            connection_response = requests.get(f'{BOOKING_URL}/connection/{str(fs.eva_number)}/{str(ts.eva_number)}/{date}', params={'skip': len(connections)}).json()
            if not connection_response['connections'] or len(connection_response['connections']) == 0:
                print(f'No matching connections found')
                return

            connection_page = [Connection.from_json(c) for c in connection_response['connections']]
            for connection in connection_page:
                if len(connections) < results:
                    departure_train = connection.get_departure_train()
                    body = {
                        "njFrom": connection.from_station.eva_number,
                        "njTo": connection.to_station.eva_number,
                        "njDep": departure_train.departure_stamp,
                        "maxChanges": 0,
                        "connections": 1,
                        "filter": { "njTrain": departure_train.ident, "njDeparture": departure_train.departure_stamp },
                        "objects": [{ "type": "person", "gender": t.gender, "birthDate": str(t.year_of_birth) + "-06-08", "cards": []} for t in self.travelers]
                    }
                    offers = Offer.from_json(requests.post(f'{BOOKING_URL}/offer/get', headers=self.default_header, json=self.default_body | body).json())

                    connections.append(connection)
                    print(f'  {len(connections)}: {connection}:')
                    print(f'  - No offers') if not offers else [print(f'  - {str(o)}') for o in offers]


        print('')


print(f'Creation date: {date.today().strftime("%Y-%m-%d")}')

travelers = [Traveler.female(1983), Traveler.male(1979), Traveler.male(2011), Traveler.male(2017)]
nightjet = Nightjet('München', 'Mailand', travelers)
nightjet.list_offers(False, '2025-10-18', 6)
nightjet.list_offers(True, '2025-10-27', 6)
# just 2 check if it works we try 2 retrieve offers close 2 now
today = (date.today() + timedelta(weeks=4)).strftime('%Y-%m-%d')
nightjet.list_offers(False, today, 3)
nightjet.list_offers(True, today, 3)
