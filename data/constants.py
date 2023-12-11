import pandas as pd
from gurobipy import *
import os

# ----- global variables -------------------------
WEIGHTPERUNIT = 2.58  # kg
NUMOFDC = 4
NUMOFRETAILER = 50
NUMOFCD = 6
NUMOFSOURCE = 3
INTEGER = "I"  # decision variable type, 'I' integer,
BINARY = "B"  # decision variable type, 'B' binary,
CONT = "C"  # decision variable 'C' continuous
BACKORDER = 50000
DC = []
CD = []
SOURCE = []
RETAILER = []
OPTIONALSOURCE = []
DATAENTRYATTS = []
CO2PRICE = 80
OPENINGCOST = 1250000
GRAMM_TO_TONNE = 1000000


path = os.path.dirname(os.path.abspath(__file__))


# ------ auxiliary functions -----------------------


# list of data entries, get location by using attribute "LocationID"
def get_data_entries():
    data_read = pd.read_csv(path + "/demand.csv", delimiter=";")
    # demand: Attribute(Demand); Role(Retailer);Location;Size; Position; Product; TimeBucketFirst; TimebucketEnd; Type; Value
    data_entries = []

    data_attribute = list(data_read["Attribute"].dropna())
    data_role = list(data_read["Role"].dropna())
    data_location = list(data_read["Location"].dropna())
    data_timeFirst = list(data_read["TimeBucketFirst"].dropna())  # str
    data_timeEnd = list(data_read["TimeBucketEnd"].dropna())  # str
    data_value = list(data_read["Value"].dropna())  # int
    data_type = list(data_read["Type"])  # str
    data_size = list(data_read["Size"])  # str
    data_position = list(data_read["Position"].dropna())  # int
    data_product = list(data_read["Product"])  # str
    for i in range(len(data_read["Location"])):
        entry = {
            "Attribute": data_attribute[i],
            "Role": data_role[i],
            "Location": data_location[i],
            "Value": data_value[i],
            "Size": data_size[i] if data_role[i] == "OptionalSource" else None,
            "Position": data_position[i],
            "Product": None if data_role[i] == "OptionalSource" else data_product[i],
            "Type": data_type[i],
        }
        data_entries.append(entry)

    return data_entries

def get_distance_data():
    distance_read = pd.read_csv(path + "/distances.csv", delimiter=";")
    distance_data = []
    for i in range(len(distance_read)):
        entry = {key: distance_read[key][i] for key in distance_read}
        distance_data.append(entry)

    # distance_data is list of distances between all connected node/ location: {start, roleStart, end, roleEnd, distance}, start and end are LocationID
    return distance_data


# distance_data is a list of dicts, each dict represents the distance of one location to another location
# [{start, roleStart, end, roleEnd, distance}, ...], start and end are LocationID


# helper function to return the distance between start location and dest location
def get_distance(distance_data, start, dest):
    for entry in distance_data:
        if entry["start"] == start and entry["end"] == dest:
            return entry["distance"]


def get_nodes():
    nodes_read = pd.read_csv(path + "/nodes.csv", delimiter=";")
    nodes = []
    for i in range(len(nodes_read)):
        entry = {key: nodes_read[key][i] for key in nodes_read}
        if entry["Role"] == "Retailer":
            RETAILER.append(entry)
        elif entry["Role"] == "CrossDock":
            CD.append(entry)
        elif entry["Role"] == "Distribution center":
            DC.append(entry)
        elif entry["Role"] == "Source":
            SOURCE.append(entry)
        elif entry["Role"] == "OptionalSource":
            OPTIONALSOURCE.append(entry)
        else:
            assert False, "In get_nodes, invalid name for Role is found: {}".format(
                entry["Role"]
            )
        nodes.append(entry)

    return nodes


def get_demands():
    demand_read = pd.read_csv(path + "/yearlyDemand.csv", delimiter=";")
    demand_data = {}
    total_demand = 0
    location, demand = demand_read.keys()
    for i in range(len(demand_read)):
        demand_data[demand_read[location][i]] = demand_read[demand][i]
        total_demand += demand_read[demand][i]

    # distance_data is list of distances between all connected node/ location: {start, roleStart, end, roleEnd, distance}, start and end are LocationID
    return demand_data, total_demand


# ---------- Parameters -------------------------------------

# nodes is list of all node/ location: {LocationID, Position, Role, NodeID}, start and end are node ID
nodes = get_nodes()
data_entries = get_data_entries()

# data_entries is now list of dicts, one dict represents one row in excel, keys are attribute names, value are values


# demands is now (20.11.2023) a dictionary, key is the location ID without _0, value is the demand
# total_demand is the sum of all demands
demands, total_demand = get_demands()


total_weight = total_demand * WEIGHTPERUNIT


# DC_constraints done, dictionary that holds the max capacity at DC "Location"
DC_constraints = dict()
for data in data_entries:
    if data["Attribute"] == "OverallCapacity" and data["Role"] == "Distribution Center":
        DC_constraints[data["Location"]] = data["Value"]


# distance_data is a list of dicts, each dict represents the distance of one location to another location
# [{start, roleStart, end, roleEnd, distance}, ...], start and end are LocationID
distance_data = get_distance_data()

distancesMap = {}
for entry in distance_data:
    if entry["start"] in distancesMap.keys():
        distancesMap[entry["start"]][entry["end"]] = entry["distance"]
    else:
        distancesMap[entry["start"]] = {entry["end"]: entry["distance"]}


DC_amount = {key["LocationID"]: 0 for key in DC}
CD_amount = {key["LocationID"]: 0 for key in CD}
SOURCE_amount = {key["LocationID"]: 0 for key in SOURCE}
OPTIONALSOURCE_amount = {key["LocationID"]: 0 for key in OPTIONALSOURCE}

# each element is the sum of the amount at one DC
# in constraint: for key in DC_amount.keys(): DC_amount[key] <= DC_constraints[key]
# sum(DC_amount.values()) == total_demand


# --- Costs, minimize, parameters in objective function ---------------------------------
transportTypes = ["air", "sea", "road"]
co2cost = {
    # per unit/kilometer
    "air": 971 / (1000 / 2.58),  # 971 for tonne
    "sea": 27 / (1000 / 2.58),  # 27 for tonne
    "road": 76 / (1000 / 2.58),  # 76 for tonne
}

slowcost = {
    # per unit/km
    "air": 0.00065,
    "sea": 0.0525,
    "road": 0.0027,
}

transportcost = {
    # per unit/km
    "air": 0.0105 * 2.58,
    "sea": 0.0013 * 2.58,
    "road": 0.0054 * 2.58,
}

# linear handling cost of DC and CD, keys are locationIDs
handlingcost = {
    data["Location"]: data["Value"]
    for data in data_entries
    if data["Attribute"] == "Handling cost"
}
print("handlingcost: ", handlingcost)

# linear sourcing cost the each source, keys are locationIDs
sourcingcost = {
    data["Location"]: data["Value"]
    for data in data_entries
    if data["Attribute"] == "Sourcing cost"
}

# linear cost to produce one unit at optional source
variablecost = {
    data["Location"]: data["Value"]
    for data in data_entries
    if data["Attribute"] == "Variable cost"
}

# binary cost of opening an optional source
openingcost = {
    data["Location"]: data["Value"]
    for data in data_entries
    if data["Attribute"] == "OpeningCost"
}

# binary cost of opening an optional source
operationalcost = {
    data["Location"]: data["Value"]
    for data in data_entries
    if data["Attribute"] == "OperatingCost"
}


locationCosts = {
    "z": sourcingcost,
    "y": handlingcost,
    "x": handlingcost,
    "o": variablecost,
}
