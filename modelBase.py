from data.constants import *
from gurobipy import *


class ElectronicManufacturerModel:
    def __init__(self, name, allTransports, withOptionalSources):
        self.withOptionalSources = withOptionalSources
        self.withAllTransport = allTransports
        self.transportTypes = ["air", "sea", "road"] if allTransports else ["air"]
        self.opt_mod = Model(name=f"{name}")
        self.os_vars = []
        self.decision_vars = []
        self.initializeBaseModel()
        self.DC_amount = {key["LocationID"]: 0 for key in DC}
        self.CD_amount = {key["LocationID"]: 0 for key in CD}
        self.SOURCE_amount = {key["LocationID"]: 0 for key in SOURCE}
        self.OPTIONALSOURCE_amount = {key["LocationID"]: 0 for key in OPTIONALSOURCE}

    def initializeBaseModel(self):
        self.addDesicionVariablesZ()
        self.addDesicionVariablesY()
        self.addDesicionVariablesX()
        if self.withOptionalSources:
            self.addDesicionVariableO()
        self.addConstraintsNonNegative()
        self.addConstraintRetailers()
        self.addConstraintDc()
        self.addConstraintCd()

    def addDesicionVariablesX(self):
        for dc in DC:
            for retailer in RETAILER:
                for k in self.transportTypes:
                    varname = (
                        "x"
                        + k
                        + str(dc["LocationID"])
                        + "-"
                        + str(retailer["LocationID"])
                    )
                    a = self.opt_mod.addVar(name=varname, vtype=INTEGER, lb=0)

                    var_entry = {
                        "var": a,
                        "part": "x",  # x = DC to retailer in supply chain
                        "start": dc["LocationID"],
                        "dest": retailer["LocationID"],
                        "mode": k,
                    }
                    self.decision_vars.append(var_entry)

    def addDesicionVariablesY(self):
        for cd in CD:
            for dc in DC:
                for k in self.transportTypes:
                    varname = (
                        "y" + k + str(cd["LocationID"]) + "-" + str(dc["LocationID"])
                    )
                    a = self.opt_mod.addVar(name=varname, vtype=INTEGER, lb=0)

                    var_entry = {
                        "var": a,
                        "part": "y",  # y = CD to DC in supply chain
                        "start": cd["LocationID"],
                        "dest": dc["LocationID"],
                        "mode": k,
                    }
                    self.decision_vars.append(var_entry)

    def addDesicionVariablesZ(self):
        for source in SOURCE:
            for cd in CD:
                for k in self.transportTypes:
                    if k == "road":
                        continue
                    varname = (
                        "z"
                        + k
                        + str(source["LocationID"])
                        + "-"
                        + str(cd["LocationID"])
                    )
                    a = self.opt_mod.addVar(name=varname, vtype=INTEGER, lb=0)

                    var_entry = {
                        "var": a,
                        "part": "z",  # z = source to CD in supply chain
                        "start": source["LocationID"],
                        "dest": cd["LocationID"],
                        "mode": k,
                    }
                    self.decision_vars.append(var_entry)

    def addDesicionVariableO(self):
        big_M = 10000000000
        for optionalSource in OPTIONALSOURCE:
            vname = "o" + str(optionalSource["LocationID"]) + "_build"
            build = self.opt_mod.addVar(name=vname, vtype=BINARY)
            os_var_entry = {
                "var": build,
                "part": "o",
                "start": optionalSource["LocationID"],
                "dest": optionalSource["LocationID"],
                "mode": "None",
            }
            self.os_vars.append(os_var_entry)
            for dc in DC:
                for k in self.transportTypes:
                    varname = (
                        "o"
                        + str(optionalSource["LocationID"])
                        + "-"
                        + str(dc["LocationID"])
                    )
                    a = self.opt_mod.addVar(name=varname, vtype=INTEGER, lb=0)

                    self.opt_mod.addConstr(a >= 0)

                    self.opt_mod.addConstr(a <= big_M * build)

                    var_entry = {
                        "var": a,
                        "part": "o",
                        "start": optionalSource["LocationID"],
                        "dest": dc["LocationID"],
                        "mode": k,
                        "build": build,
                    }
                    self.decision_vars.append(var_entry)

    def addConstraintsNonNegative(self):
        for j in self.decision_vars:
            self.opt_mod.addConstr(j["var"] >= 0)

    def addConstraintRetailers(self):
        for retailer in demands:
            self.opt_mod.addConstr(
                sum(
                    list(
                        j["var"]
                        for j in self.decision_vars
                        if j["part"] == "x" and j["dest"] == retailer
                    )
                )
                == demands[retailer]
            )

    def addConstraintCd(self):
        for cd in CD:
            amount_cd = sum(
                list(
                    j["var"]
                    for j in self.decision_vars
                    if j["part"] == "y" and j["start"] == cd["LocationID"]
                )
            )
            self.opt_mod.addConstr(
                sum(
                    list(
                        j["var"]
                        for j in self.decision_vars
                        if j["part"] == "z" and j["dest"] == cd["LocationID"]
                    )
                )
                == amount_cd
            )

    def addConstraintDc(self):
        for dc in DC:
            amount_dc = sum(
                list(
                    j["var"]
                    for j in self.decision_vars
                    if j["part"] == "x" and j["start"] == dc["LocationID"]
                )
            )
            self.opt_mod.addConstr(amount_dc <= DC_constraints[dc["LocationID"]])
            self.opt_mod.addConstr(
                sum(
                    list(
                        j["var"]
                        for j in self.decision_vars
                        if j["part"] == "y"
                        and j["dest"] == dc["LocationID"]
                        or j["part"] == "o"
                        and j["dest"] == dc["LocationID"]
                    )
                )
                == amount_dc
            )

    def addCo2Const(self, upperBoundCo2):
        self.opt_mod.addConstr(
            sum(
                v["var"] * co2cost[v["mode"]] * distancesMap[v["start"]][v["dest"]]
                for v in self.decision_vars
            )
            / GRAMM_TO_TONNE
            <= upperBoundCo2
        )

    def getOptimalvalue(self):
        return self.opt_mod.ObjVal

    def getCo2EmissionsInT(self):
        totalEmission = (
            sum(
                v["var"].x * co2cost[v["mode"]] * distancesMap[v["start"]][v["dest"]]
                for v in self.decision_vars
            )
            / GRAMM_TO_TONNE
        )
        return totalEmission

    def getCo2EmissionZ(self):
        emissions = sum(
            (v["var"].x if v["part"] == "z" else 0)
            * distancesMap[v["start"]][v["dest"]]
            * co2cost[v["mode"]]
            for v in self.decision_vars
        )
        return emissions / GRAMM_TO_TONNE

    def getCo2EmissionY(self):
        emissions = sum(
            (v["var"].x if v["part"] == "y" else 0)
            * distancesMap[v["start"]][v["dest"]]
            * co2cost[v["mode"]]
            for v in self.decision_vars
        )
        return emissions / GRAMM_TO_TONNE

    def getCo2EmissionO(self):
        emissions = sum(
            (v["var"].x if v["part"] == "o" else 0)
            * distancesMap[v["start"]][v["dest"]]
            * co2cost[v["mode"]]
            for v in self.decision_vars
        )
        return emissions / GRAMM_TO_TONNE

    def getCo2EmissionX(self):
        emissions = sum(
            (v["var"].x if v["part"] == "x" else 0)
            * distancesMap[v["start"]][v["dest"]]
            * co2cost[v["mode"]]
            for v in self.decision_vars
        )
        return emissions / GRAMM_TO_TONNE

    def getTotalCost(self):
        totalCost = sum(
            j["var"].x
            * (
                distancesMap[j["start"]][j["dest"]]
                * (
                    transportcost[j["mode"]]
                    + (slowcost[j["mode"]] if self.withAllTransport else 0)
                )
                + locationCosts[j["part"]][j["start"]]
            )
            for j in self.decision_vars
        )
        for j in self.os_vars:
            if j["part"] == "o":
                totalCost += j["var"].x * OPENINGCOST

        return totalCost

    def getTransportCost(self):
        transportC = sum(
            v["var"].x * distancesMap[v["start"]][v["dest"]] * transportcost[v["mode"]]
            for v in self.decision_vars
        )
        return transportC

    def getSlownesCost(self):
        slownessCost = sum(
            v["var"].x * distancesMap[v["start"]][v["dest"]] * slowcost[v["mode"]]
            for v in self.decision_vars
        )
        return slownessCost

    def getSourcingCost(self):
        sourcingCosts = sum(
            (v["var"].x * locationCosts[v["part"]][v["start"]])
            if v["part"] == "z"
            else 0
            for v in self.decision_vars
        )
        return sourcingCosts

    def getHandlingCostCd(self):
        handlingCosts = sum(
            (v["var"].x * locationCosts[v["part"]][v["start"]])
            if v["part"] == "y"
            else 0
            for v in self.decision_vars
        )
        return handlingCosts

    def getHandlingCostDc(self):
        handlingCosts = sum(
            (v["var"].x * locationCosts[v["part"]][v["start"]])
            if v["part"] == "x"
            else 0
            for v in self.decision_vars
        )
        return handlingCosts

    def getVariableCost(self):
        variableCost = sum(
            (v["var"].x * locationCosts[v["part"]][v["start"]])
            if v["part"] == "o"
            else 0
            for v in self.decision_vars
        )
        return variableCost

    def getOpeningCosts(self):
        costs = 0
        for v in self.os_vars:
            costs += OPENINGCOST * v["var"].x

        return costs

    def getLocationAmounts(self):
        for v in self.decision_vars:
            if v["part"] == "x":
                self.DC_amount[v["start"]] += v["var"].x
            elif v["part"] == "y":
                self.CD_amount[v["start"]] += v["var"].x
            elif v["part"] == "z":
                self.SOURCE_amount[v["start"]] += v["var"].x
            else:
                self.OPTIONALSOURCE_amount[v["start"]] += v["var"].x

    def report(self):
        with open(f"{self.opt_mod.modelName}.txt", "w") as file:
            file.write("\n")
            file.write("----------- start report ----------")
            file.write("\n")
            file.write(f"Objective Function Value: {self.getOptimalvalue()}")
            file.write("\n")
            file.write("------- Nodes --------")
            file.write("\n")
            for v in self.opt_mod.getVars():
                if (
                    v.varName.startswith("x")
                    or v.varName.startswith("y")
                    or v.varName.startswith("z")
                    or v.varName.startswith("o")
                ):
                    if v.x != 0:
                        file.write(f"{v.varName}: {v.x}\n")
            file.write("\n")
            file.write("------- Costs --------\n")
            file.write("\n")
            file.write(
                f"Total cost without Co2 compensation: {self.getTotalCost()} Euro\n"
            )
            if self.withAllTransport:
                file.write(f"Slowness cost: {self.getSlownesCost()} Euro\n")
            file.write(f"Transportation cost: {self.getTransportCost()} Euro\n")
            file.write(f"Sourcing costs: {self.getSourcingCost()} Euro\n")
            file.write(
                f"Handling costs at cross docs: {self.getHandlingCostCd()} Euro\n"
            )
            file.write(
                f"Handling costs at distribution centers: {self.getHandlingCostDc()} Euro\n"
            )
            file.write(
                f"Variable costs at optional source: {self.getVariableCost()} Euro\n"
            )
            file.write(
                f"Opening costs at optional source: {self.getOpeningCosts()} Euro\n"
            )
            file.write("\n")
            file.write("------- Emissions -------\n")
            file.write("\n")
            file.write(
                f"Total cost with emission compensation: {self.getCo2EmissionsInT() * CO2PRICE + self.getTotalCost()} Euro\n"
            )
            file.write(f"Total Co2 emissions: {self.getCo2EmissionsInT()} t\n")
            file.write(
                f"Cost for compensation: {self.getCo2EmissionsInT() * CO2PRICE} Euro\n"
            )
            file.write(
                f"Emissions between retailer and cross doc: {self.getCo2EmissionZ()} t\n"
            )
            file.write(
                f"Emissions between cross doc and dsitribution center: {self.getCo2EmissionY()} t\n"
            )
            file.write(
                f"Emissions between optional source and distribution center: {self.getCo2EmissionO()} t\n"
            )
            file.write(
                f"Emissions between distribution center and retailer: {self.getCo2EmissionX()} t\n"
            )
            self.getLocationAmounts()
            file.write("\n")
            file.write(("--------- Amouts --------\n"))
            file.write("\n")
            file.write(f"Sources: {self.SOURCE_amount}\n")
            file.write(f"Cross Docs: {self.CD_amount}\n")
            file.write(f"Distribution centers: {self.DC_amount}\n")
            file.write(f"Demands ad retailers: {demands}\n")
            file.write(f"Optional sources: {self.OPTIONALSOURCE_amount}\n")
            file.write("\n")
            file.write("--------- end report ------------\n")
            file.write("\n")

    def setOpjectivefunctionMinimize(self, minFunction):
        obj_func = minFunction()
        self.opt_mod.setObjective(obj_func, GRB.MINIMIZE)

    def minCostAir(self):
        minCosts = sum(
            j["var"]
            * (
                distancesMap[j["start"]][j["dest"]] * transportcost["air"]
                + locationCosts[j["part"]][j["start"]]
            )
            for j in self.decision_vars
        )
        return minCosts

    def minCostAlltransport(self):
        minCosts = sum(
            j["var"]
            * (
                distancesMap[j["start"]][j["dest"]]
                * (transportcost[j["mode"]] + slowcost[j["mode"]])
                + locationCosts[j["part"]][j["start"]]
            )
            for j in self.decision_vars
        )
        return minCosts

    def minCo2Cost(self):
        minCosts = (
            CO2PRICE
            * sum(
                j["var"] * distancesMap[j["start"]][j["dest"]] * co2cost[j["mode"]]
                for j in self.decision_vars
            )
            / GRAMM_TO_TONNE
        )
        return minCosts

    def minEmissions(self):
        minEmissions = (
            sum(
                j["var"] * distancesMap[j["start"]][j["dest"]] * co2cost[j["mode"]]
                for j in self.decision_vars
            )
            / GRAMM_TO_TONNE
        )

        return minEmissions

    def minOpenincost(self):
        costs = 0
        for v in self.os_vars:
            costs += v["var"] * OPENINGCOST
        return costs

    def minCostAlltransportOs(self):
        func1 = self.minCostAlltransport()
        func2 = self.minOpenincost()
        return func1 + func2

    def minCo2CostAlltransportOs(self):
        func1 = self.minCo2Cost()
        func2 = self.minCostAlltransport()
        func3 = self.minOpenincost()
        return func1 + func2 + func3

    def minCo2CostAlltransport(self):
        func1 = self.minCo2Cost()
        func2 = self.minCostAlltransport()
        return func1 + func2

    def minCo2CostAirOs(self):
        func1 = self.minCostAir()
        func2 = self.minOpenincost()
        return func1 + func2

    def minCostAirOs(self):
        func1 = self.minCostAir()
        func2 = self.minOpenincost()
        return func1 + func2


scenario1 = ElectronicManufacturerModel("Scenario1", False, False)
scenario1.setOpjectivefunctionMinimize(scenario1.minCostAir)
scenario1.opt_mod.optimize()
scenario1.report()

scenario2 = ElectronicManufacturerModel("Scenario2", False, True)
scenario2.setOpjectivefunctionMinimize(scenario2.minCostAirOs)
scenario2.opt_mod.optimize()
scenario2.report()

scenario3 = ElectronicManufacturerModel("Scenario3", True, True)
scenario3.setOpjectivefunctionMinimize(scenario3.minCo2CostAlltransportOs)
scenario3.opt_mod.optimize()
scenario3.report()
