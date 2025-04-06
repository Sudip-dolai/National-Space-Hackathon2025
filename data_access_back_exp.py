import csv
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.responses import FileResponse
from operator import itemgetter
from datetime import datetime
from datetime import date
from io import StringIO
import pytz
import uuid  # To generate unique IDs

app = FastAPI()

# ✅ Enable CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# accessing today's date
today = str(date.today())
now = datetime.now(pytz.timezone('Asia/Kolkata'))

# temporary item details
placementItemDetail = {}

# User Id
originalUserId = "nsh@user001"

# temporary
tempPlacementDatabase = {}

# In-memory database to store multiple users
placeDatabase = {}
itemDataReadCsv = []

#
containerDetails = []
containerDataReadCsv = []

# memory of ocupied place in container 
containerDatabase = {}

# blockedItem storage
blockedData = []

# log data
logData = []

# item details list
itemDataCSV = [["Item ID", "Container ID", "StartCoordinates (W1,D1,H1)", "EndCoordinates(W2,D2,H2)"]]

# waste item list
wasteitemList = {}

# placement data input format
class itemData(BaseModel):
    itemId: str
    name: str
    width: int
    depth: int
    height: int
    mass: int  # added last
    priority: int
    expiryDate: str
    usageLimit: int
    preferredZone: str
class containerData(BaseModel):
    containerId: str
    zone: str
    width: int
    depth: int
    height:int
    ocupiedPlace: list
class combPlacementData(BaseModel):
    item: itemData
    container: containerData

# place data input format
class plaseStartPosition(BaseModel):
    width: int
    depth: int
    height: int
class plaseEndPosition(BaseModel):
    width: int
    depth: int
    height: int
class placePosition(BaseModel):
    startCoordinates: plaseStartPosition
    endCoordinates: plaseEndPosition
class placeData(BaseModel):
    itemId: str
    userId: str
    timestamp: str
    containerId: str
    position: placePosition

# retrieve
class retrieveData(BaseModel):
    itemId: str
    userId: str
    timestamp: str

class logDate(BaseModel):
    startDate: str
    endDate: str

# searching location in containerDetails by itemId
def searchLocationById(id):
    contIdx = -1
    for idx, cont in enumerate(containerDetails):
        if cont["containerId"] == placeDatabase[id]["containerId"] :
            contIdx = idx
            break
    for idx, item in enumerate(containerDetails[contIdx]["ocupiedPlace"]):
        if item[0] == id :
            return idx
    return -1
        



# 3D Bin-packing algorithm
class CargoBin:
    def __init__(self, width, depth, height, usedPlace):
        self.width = width
        self.depth = depth
        self.height = height
        self.storedItems = usedPlace  # Stores placed items with coordinates

    def fits(self, item, x, y, z):
        # Check if the item fits within the bin at the given position without overlapping
        if x + item["width"] > self.width or y + item["depth"] > self.depth or z + item["height"] > self.height:
            return False
        
        # Check for collisions with already placed items
        for placed in self.storedItems:
            if not (
                # """ new item at left placed[s][x] rt placed[e][x]"""
                x + item["width"] <= placed[1][0] or placed[2][0] <= x or
                y + item["depth"] <= placed[1][1] or placed[2][1] <= y or
                z + item["height"] <= placed[1][2] or placed[2][2] <= z
            ):
                return False
        return True

    def add_item(self, item):
        # Try placing the item in the first available space using BLB heuristic
        for y in range(self.depth):
            for z in range(self.height):
                for x in range(self.width):
                    if self.fits(item, x, y, z):
                        print(f"Item placed at ({x}, {y}, {z})")
                        return {"success": True, "itemLocation": [[x,y,z],[x+item["width"], y+item["depth"], z+item["height"]]]}
        print("No space available for item!")
        return {"success": False}


# containerDetails = [{"containerId": "contA", "zone": "crewQuarter", "width": 100, "depth": 100, "height": 200, "ocupiedPlace": [["item", [0,0,0], [20,30,40]]]}]
# ocupiedPlace": [["item", [0,0,0], [20,30,40]]]

# Retrieval process: searching for blockage items
# {
 #   "startCoord":[]
 #   "endCoord": []
 # }
class cargoRetrieve:
    def __init__(self, usedPlace):
        self.storedItems = usedPlace
    def searchBlock(self, item):
        if item["startCoord"][1] == 0:
            return False
        for stItem in self.storedItems:
            if stItem[2][1] <= item["startCoord"][1]:
                if stItem[2][0] >= item["startCoord"][0] and stItem[1][0] <= item["endCoord"][0]: # x-axis
                    if stItem[2][2] >= item["startCoord"][2] and stItem[1][2] <= item["endCoord"][2]: # z-axis
                        inputItem = {
                            "startCoord": [placeDatabase[stItem[0]]["position"]["startCoordinates"]["width"], placeDatabase[stItem[0]]["position"]["startCoordinates"]["depth"], placeDatabase[stItem[0]]["position"]["startCoordinates"]["height"]],
                            "endCoord": [placeDatabase[stItem[0]]["position"]["endCoordinates"]["width"], placeDatabase[stItem[0]]["position"]["endCoordinates"]["depth"], placeDatabase[stItem[0]]["position"]["endCoordinates"]["height"]]
                        }
                        self.searchBlock(inputItem)
                        if [stItem[0], placeDatabase[stItem[0]]["itemDetail"]["name"]] not in blockedData:
                            blockedData.append([stItem[0], placeDatabase[stItem[0]]["itemDetail"]["name"]])             
        return True


# Check for waste items
def checkWaste(itemId):
    if itemId not in wasteitemList:
        if datetime.strptime(placeDatabase[itemId]["itemDetail"]["expiryDate"], "%Y-%m-%d") <= datetime.strptime(today, "%Y-%m-%d"):
            wasteItemdetail = {
                "itemId": itemId, 
                "name": placeDatabase[itemId]["itemDetail"]["name"],
                "reason": "Expired",     # "Expired", "Out of Uses"
                "containerId": placeDatabase[itemId]["containerId"],
                "position": placeDatabase[itemId]["position"]
            }
            wasteitemList[itemId] = wasteItemdetail
    return


# placement
@app.post("/placement/")
async def placement(data: itemData):
    global selectedContIndex
    
    placedCont = ""
    placementRec = {}
    if data.itemId in placeDatabase:
        for stIdx, ocupiedPls in enumerate(containerDatabase[placeDatabase[data.itemId]["containerId"]]["ocupiedPlace"]):
            if ocupiedPls[0] == data.itemId:
                del containerDatabase[placeDatabase[data.itemId]["containerId"]]["ocupiedPlace"][stIdx]
                break
        searchCompleted = False
        for idx, cont in enumerate(containerDetails):
            if cont["containerId"] == placeDatabase[data.itemId]["containerId"]:
                for stIdx, ocupiedPls in enumerate(cont["ocupiedPlace"]):
                    if ocupiedPls[0] == data.itemId:
                        del containerDetails[idx]["ocupiedPlace"][stIdx]
                        break
                if searchCompleted:
                    break

    for idx, cont in enumerate(containerDetails):
        if cont["zone"] != data.preferredZone:
            continue
        cargoCont = CargoBin(cont["width"], cont["depth"], cont["height"], cont["ocupiedPlace"])
        placementRec = cargoCont.add_item({"width": data.width, "depth": data.depth, "height": data.height})
        if placementRec["success"] :
            placedCont = cont["containerId"]
            selectedContIndex = idx
            break

    x0,y0,z0, x1,y1,z1 = -1,-1,-1, -2,-2,-2
    if placementRec["success"] :
        x0 = placementRec["itemLocation"][0][0]
        y0 = placementRec["itemLocation"][0][1]
        z0 = placementRec["itemLocation"][0][2]
        x1 = placementRec["itemLocation"][1][0]
        y1 = placementRec["itemLocation"][1][1]
        z1 = placementRec["itemLocation"][1][2]
    placementDetail = {
        "itemId": data.itemId,
        "containerId": placedCont,
        "position": {
            "startCoordinates": {
                "width": x0,
                "depth": y0,
                "height": z0
            },
            "endCoordinates": {
                "width": x1,
                "depth": y1,
                "height": z1
            }
        }
    }

    placementItemDetail["name"] = data.name
    placementItemDetail["mass"] = data.mass  # added last
    placementItemDetail["priority"] = data.priority
    placementItemDetail["expiryDate"] = data.expiryDate
    placementItemDetail["usageLimit"] = data.usageLimit
    placementItemDetail["preferredZone"] = data.preferredZone

    return {"success": True, "placement": placementDetail}


@app.post("/place/")
async def place(data: placeData):
    if data.userId != originalUserId :
        return {"success": False, "message": "Wrong user Id"}
    itemId = data.itemId
    containerId = data.containerId
    placeDatabase.setdefault(itemId, {})["itemId"] = data.itemId
    placeDatabase[itemId]["containerId"] = data.containerId
    placeDatabase[itemId]["timestamp"] = data.timestamp
    placeDatabase[itemId]["itemDetail"] = {
        "name": placementItemDetail["name"],
        "mass": placementItemDetail["mass"],  # added last
        "priority": placementItemDetail["priority"],
        "expiryDate": placementItemDetail["expiryDate"],
        "usageLimit": placementItemDetail["usageLimit"],
        "preferredZone": placementItemDetail["preferredZone"]
    }

    placeDatabase[itemId]["position"] = data.position.dict()

    x0 = data.position.startCoordinates.width
    y0 = data.position.startCoordinates.depth
    z0 = data.position.startCoordinates.height
    x1 = data.position.endCoordinates.width
    y1 = data.position.endCoordinates.depth
    z1 = data.position.endCoordinates.height

    containerDatabase.setdefault(containerId, {})["ocupiedPlace"].append([itemId,[x0,y0,z0],[x1,y1,z1]])
    containerDetails[selectedContIndex]["ocupiedPlace"].append([itemId,[x0,y0,z0],[x1,y1,z1]])

    for idx, arrangement in enumerate(itemDataCSV):
        if arrangement[0] == itemId:
            del itemDataCSV[idx]
            break


    stCoord = "(" + str(x0) + "," + str(y0) + "," + str(z0) + ")"
    enCoord = "(" + str(x1) + "," + str(y1) + "," + str(z1) + ")"

    itemDataCSV.append([itemId, data.containerId, stCoord, enCoord])

    log = {
        "timestamp": data.timestamp,
        # "userId": data.userId,
        "actionType": "placement",
        "itemId": data.itemId,
        "details": {
            "toContainer": data.containerId
        }
    }

    logData.append(log)

    return {"success": True, "storage": placeDatabase , "container": containerDatabase, "logs": logData}


@app.post("/addCont/")
async def addcont(data: containerData):
    # tempContData = data.dict()
    containerDatabase[data.containerId] = data.dict()
    alreadyExistCont = False
    for idx, cont in enumerate(containerDetails):
        if cont["containerId"] == data.containerId:
            alreadyExistCont = True
            del containerDetails[idx]
            containerDetails.append(data.dict())
            break
    if not alreadyExistCont:
        containerDetails.append(data.dict())
    return {"success": True, "containerStorage": containerDetails, "containerDatabase": containerDatabase}



@app.get("/search/{searchData}")
async def search(searchData: str):
    searchItemName = ""
    if searchData[0:3] == "id-":
        searchItemName = placeDatabase[searchData[3:]]["itemDetail"]["name"]
    else: searchItemName = searchData[3:]

    found = False
    nearExpDate = datetime.strptime("2125-01-01", "%Y-%m-%d")
    itemRecommanded = ""
    
    for item in list(placeDatabase.values()):
        if item["itemDetail"]["name"] == searchItemName and item["itemId"] not in wasteitemList :
            found = True
            if datetime.strptime(item["itemDetail"]["expiryDate"], "%Y-%m-%d") < nearExpDate:
                nearExpDate = datetime.strptime(item["itemDetail"]["expiryDate"], "%Y-%m-%d")
                itemRecommanded = item["itemId"]

    if found:
        itemDetails = {
            "itemId": itemRecommanded,
            "name": placeDatabase[itemRecommanded]["itemDetail"]["name"],
            "containerId": placeDatabase[itemRecommanded]["containerId"],
            "zone": placeDatabase[itemRecommanded]["itemDetail"]["preferredZone"],
            "position": placeDatabase[itemRecommanded]["position"]
        }
        itemBlockageSerch = cargoRetrieve(containerDatabase[itemDetails["containerId"]]["ocupiedPlace"])
        inputItem = {
            "startCoord": [placeDatabase[itemRecommanded]["position"]["startCoordinates"]["width"], placeDatabase[itemRecommanded]["position"]["startCoordinates"]["depth"], placeDatabase[itemRecommanded]["position"]["startCoordinates"]["height"]],
            "endCoord": [placeDatabase[itemRecommanded]["position"]["endCoordinates"]["width"], placeDatabase[itemRecommanded]["position"]["endCoordinates"]["depth"], placeDatabase[itemRecommanded]["position"]["endCoordinates"]["height"]]
        }
        
        blockedData.clear()
        checkBlock = itemBlockageSerch.searchBlock(inputItem)
        return {"success": True, "found": found, "itemDetails": itemDetails, "retrievalSteps": blockedData, "checkBlock": checkBlock}
    return {"success": False}




@app.post("/retrieve/")
async def retrieve(data: retrieveData):
    usageLimit = placeDatabase[data.itemId]["itemDetail"]["usageLimit"]
    usageLimit -= 1
    if usageLimit != 0:
        placeDatabase[data.itemId]["itemDetail"]["usageLimit"] = usageLimit
    else:
        wasteItemdetail = {
            "itemId": data.itemId,
            "name": placeDatabase[data.itemId]["itemDetail"]["name"],
            "reason": "Outof Uses",     #"Expired", "Outof Uses"
            "containerId": placeDatabase[data.itemId]["containerId"],
            "position": placeDatabase[data.itemId]["position"]
        }
        wasteitemList[data.itemId] = wasteItemdetail


    log = {
        "timestamp": data.timestamp,
        # "userId": data.userId,
        "actionType": "retrieval",
        "itemId": data.itemId,
        "details": {
            "fromContainer": placeDatabase[data.itemId]["containerId"]
        }
    }

    logData.append(log)

    return {"success": True, "usageLimit": placeDatabase[data.itemId]["itemDetail"]["usageLimit"]}
    


@app.get("/waste_identify/")
async def waste_identify():
    for item in placeDatabase:
        checkWaste(item)

    return {"wasteList": wasteitemList}


@app.get("/export_arrangement_csv/")
async def export_arrangement_csv():

    filename = "Current_arrangement_" + str(now.year) + str(now.month) + str(now.day) + "_" + str(now.hour) + str(now.minute) + str(now.second) + ".csv"
    
    with open(filename, mode="w", newline="") as file:
        writer = csv.writer(file)
        writer.writerows(itemDataCSV)

    return FileResponse(path=filename, filename=filename, media_type="text/csv")



@app.post("/upload_item_csv/")
async def upload_item_csv(file: UploadFile = File(...)):
    content = await file.read()                      # Read file bytes
    decoded = content.decode('utf-8')                # Decode to string
    csv_reader = csv.reader(StringIO(decoded))       # Use StringIO to simulate file
    rows = [row for row in csv_reader]               # Convert to list

    for idx, csvElement in enumerate(rows):
        if idx == 0: continue
        dictReadCsv = {
            "itemId": str(csvElement[0]),
            "name": str(csvElement[1]),
            "width": int(csvElement[2]),
            "depth": int(csvElement[3]),
            "height": int(csvElement[4]),
            "mass": int(csvElement[5]),
            "priority": int(csvElement[6]),
            "expiryDate": str(csvElement[7]),
            "usageLimit": int(csvElement[8]),
            "preferredZone": str(csvElement[9])
        }
        itemDataReadCsv.append(dictReadCsv)

    sortedItemDataReadCsv = sorted(itemDataReadCsv, key=itemgetter("priority"), reverse = True)
    for item in sortedItemDataReadCsv:
        for contIdx, cont in enumerate(containerDetails):
            if cont["zone"] != item["preferredZone"]:
                continue
            cargoCont = CargoBin(cont["width"], cont["depth"], cont["height"], cont["ocupiedPlace"])
            placementRec = cargoCont.add_item({"width": item["width"], "depth": item["depth"], "height": item["height"]})
            if placementRec["success"] == True:
                placeDatabase.setdefault(item["itemId"], {})["itemId"] = item["itemId"]
                placeDatabase[item["itemId"]]["containerId"] = cont["containerId"]
                placeDatabase[item["itemId"]]["timestamp"] = datetime.today()
                placeDatabase[item["itemId"]].setdefault("itemDetail", {})["name"] = item["name"]
                placeDatabase[item["itemId"]]["itemDetail"]["mass"] = item["mass"]   # added last
                placeDatabase[item["itemId"]]["itemDetail"]["priority"] = item["priority"]
                placeDatabase[item["itemId"]]["itemDetail"]["expiryDate"] = item["expiryDate"]
                placeDatabase[item["itemId"]]["itemDetail"]["usageLimit"] = item["usageLimit"]
                placeDatabase[item["itemId"]]["itemDetail"]["preferredZone"] = item["preferredZone"]

                x0 = placementRec["itemLocation"][0][0]
                y0 = placementRec["itemLocation"][0][1]
                z0 = placementRec["itemLocation"][0][2]
                x1 = placementRec["itemLocation"][1][0]
                y1 = placementRec["itemLocation"][1][1]
                z1 = placementRec["itemLocation"][1][2]

                placeDatabase[item["itemId"]].setdefault("position", {}).setdefault("startCoordinates", {})["width"] = x0
                placeDatabase[item["itemId"]]["position"]["startCoordinates"]["depth"] = y0
                placeDatabase[item["itemId"]]["position"]["startCoordinates"]["height"] = z0
                placeDatabase[item["itemId"]]["position"].setdefault("endCoordinates", {})["width"] = x1
                placeDatabase[item["itemId"]]["position"]["endCoordinates"]["depth"] = y1
                placeDatabase[item["itemId"]]["position"]["endCoordinates"]["height"] = z1

                containerDatabase.setdefault(cont["containerId"], {})["ocupiedPlace"].append([item["itemId"],[x0,y0,z0],[x1,y1,z1]])
                containerDetails[contIdx]["ocupiedPlace"].append([item["itemId"], [x0,y0,z0], [x1,y1,z1]])
                
                stCoord = "(" + str(x0) + "," + str(y0) + "," + str(z0) + ")"
                enCoord = "(" + str(x1) + "," + str(y1) + "," + str(z1) + ")"

                itemDataCSV.append([item["itemId"], cont["containerId"], stCoord, enCoord])

                log = {
                    "timestamp": placeDatabase[item["itemId"]]["timestamp"],
                    # "userId": data.userId,
                    "actionType": "placement",
                    "itemId": item["itemId"],
                    "details": {
                        "toContainer": cont["containerId"]
                    }
                }
                logData.append(log)

                break

    return {"data": rows, "storedData": itemDataReadCsv, "sortedStoredData": sortedItemDataReadCsv, "storage": placeDatabase, "containerDetails": containerDetails}



@app.post("/upload_cont_csv/")
async def upload_cont_csv(file: UploadFile = File(...)):
    content = await file.read()                      # Read file bytes
    decoded = content.decode('utf-8')                # Decode to string
    csv_reader = csv.reader(StringIO(decoded))       # Use StringIO to simulate file
    rows = [row for row in csv_reader]               # Convert to list

    for idx, csvElement in enumerate(rows):
        if idx == 0: continue
        dictReadCsv = {
            "containerId": str(csvElement[0]),
            "zone": str(csvElement[1]),
            "width": int(csvElement[2]),
            "depth": int(csvElement[3]),
            "height": int(csvElement[4]),
            "ocupiedPlace": []
        }
        containerDetails.append(dictReadCsv)
        containerDatabase[dictReadCsv["containerId"]] = dictReadCsv
        containerDataReadCsv.append(dictReadCsv)
    return {"success": True, "containerDetails": containerDetails, "containerDatabase": containerDatabase}



@app.post("/log_file_csv/")
def log_file_csv(data: logDate):
    filename = "Logfile_" + str(now.year) + str(now.month) + str(now.day) + "_" + str(now.hour) + str(now.minute) + str(now.second) + ".csv"
    
    logDataCSV = [["timestamp", "actionType", "itemId", "toContainer"]]

    # start_date = datetime.strptime(data.startDate, "%Y-%m-%d")
    # end_date = datetime.strptime(data.endDate, "%Y-%m-%d")
    for log in logData:
        # if datetime.strptime(log["timestamp"], "%Y-%m-%d") >= datetime.strptime(data.startDate, "%Y-%m-%d") and datetime.strptime(log["timestamp"], "%Y-%m-%d") <= datetime.strptime(data.endDate, "%Y-%m-%d"):   
        logDataCSV.append([log["timestamp"], log["actionType"], log["itemId"], log["details"]["toContainer"]])

    with open(filename, mode="w", newline="") as file:
        writer = csv.writer(file)
        writer.writerows(logDataCSV)

    return FileResponse(path=filename, filename=filename, media_type="text/csv")





if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)








