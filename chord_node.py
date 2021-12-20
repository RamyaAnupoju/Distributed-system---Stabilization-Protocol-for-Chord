import socket
import threading
import time
import hashlib
import random
import sys
import pickle
import json
import subprocess

m = 7


# The class DataStore is used to store the key value pairs at each node
class DataStore:
    def __init__(self):
        self.data = {}

    def insert(self, key, value):
        self.data[key] = value

    def search(self, search_key):
        if search_key in self.data:
            return self.data[search_key]
        else:
            return None


# Class represents the actual Node, it stores ip and port of a node
class NodeInfo:
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port

    def __str__(self):
        return self.ip + "|" + str(self.port)


# The class Node is used to manage the each node that, it contains all the information about the node like ip, port,
# the node's successor, finger table, predecessor etc. 
class Node:
    def __init__(self, ip, port):
        self.ip = ip
        self.port = int(port)
        self.nodeinfo = NodeInfo(ip, port)
        self.id = self.hash(str(self.nodeinfo))
        self.predecessor = None
        self.successor = None
        self.finger_table = FingerTable(self.id)
        self.data_store = DataStore()
        self.request_handler = RequestHandler()

    def hash(self, message):
        '''
        This function is used to find the id of any string and hence find it's correct position in the ring
        '''
        digest = hashlib.sha1(message.encode()).hexdigest()
        digest = int(digest, 16) % pow(2, m)
        return digest

    def process_requests(self, message):
        '''
        The process_requests function is used to manage the differnt requests coming to any node it checks the mesaage
        and then calls the required function accordingly
        '''
        operation = message.split("|")[0]
        args = []
        if (len(message.split("|")) > 1):
            args = message.split("|")[1:]
        result = "Done"
        if operation == 'insert_server':
            data = message.split('|')[1].split(":", 1)
            key = data[0]
            value = data[1]
            self.data_store.insert(key, value)

        if operation == "search_server":
            data = message.split('|')[1]
            if data in self.data_store.data:
                return self.data_store.data[data]
            else:
                return "NOT FOUND"

        if operation == "send_keys":
            id_of_joining_node = int(args[0])
            result = self.send_keys(id_of_joining_node)

        if operation == "insert":
            data = message.split('|')[1].split(":", 1)
            key = data[0]
            value = json.loads(data[1])
            result = self.insert_key(key, value)

        if operation == 'search':
            data = message.split('|')[1]
            result = self.search_key(data)

        if operation == "join_request":
            result = self.join_request_from_other_node(int(args[0]))

        if operation == "find_predecessor":
            result = self.find_predecessor(int(args[0]))

        if operation == "find_successor":
            result = self.find_successor(int(args[0]))

        if operation == "get_successor":
            result = self.get_successor()

        if operation == "get_predecessor":
            result = self.get_predecessor()

        if operation == "get_id":
            result = self.get_id()

        if operation == "update_predecessor":
            data = message.split('|')[1].split(":", 1)
            ip = data[0]
            port = json.loads(data[1])
            result = self.update_predecessor(ip, port)

        if operation == "update_successor":
            data = message.split('|')[1].split(":", 1)
            ip = data[0]
            port = json.loads(data[1])
            result = self.update_successor(ip, port)

        if operation == "update_tables":
            self.update_otherTables(int(args[0]))
            return

        if operation == "notify":
            self.notify(int(args[0]),args[1],args[2])

        return str(result)

    def serve_requests(self, conn, addr):
        '''
        The serve requests function is used to listen for inbound requests
        on an open port and then respond to them. It accepts the connection
        and the address of the connected device as inputs.
        '''
        try:
            with conn:
                # print('Connected by', addr)
                data = conn.recv(1048576)
                data = str(pickle.loads(data))
                data = data.strip('\n')
                data = self.process_requests(data)
                data = pickle.dumps(data)
                conn.sendall(data)
        except:
            pass

    def start(self):
        try:
            '''
            1 thread to print ID, Successor , predecessor  & data store
            '''
            thread_for_stabalize = threading.Thread(target = self.stabilize)
            thread_for_stabalize.start()
            thread_for_fix_finger = threading.Thread(target=  self.fix_fingers)
            thread_for_fix_finger.start()
            print_thread = threading.Thread(target = self.print_data)
            print_thread.start()

            
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((self.nodeinfo.ip, self.nodeinfo.port))
                s.listen()
                while True:
                    try:
                        conn, addr = s.accept()
                        t = threading.Thread(target=self.serve_requests, args=(conn, addr))
                        t.start()
                    except:
                        pass
        except:
            pass

    def print_data(self):
        """
        This method is used to print the finger table
        successor, predesessor and node id
        """
        while True:
            print("-------------------------------------------------------")
            """ while True: """
            print("ID: ", self.id)
            if self.successor is not None:
                print("Successor ID: ", self.successor.id)
            if self.predecessor is not None:
                print("predecessor ID: ", self.predecessor.id)
            print()
            print("---------------------FINGER TABLE----------------------")
            self.finger_table.print()
            print("-------------------------------------------------------")
            print("Keys \n")
            print("-------------------------------------------------------")
            print(str(self.data_store.data))
            print("-------------------------------------------------------")
            time.sleep(10)

    def stabilize(self):
        '''
        The stabilize function is called repeatedly and at regular intervals to 
        ensure that each node is pointing to the right successor and predecessor 
        nodes. Each node can use the stabilize function to gather information 
        about new nodes joining the ring.
        '''
        time.sleep(10)
        while True:
            try:
                if self.successor is None:
                    time.sleep(1)
                    continue
                data = "get_predecessor"

                if self.successor.ip == self.ip  and self.successor.port == self.port:
                    time.sleep(1)
                result = self.request_handler.send_message(self.successor.ip , self.successor.port , data)
                if result == "None" or len(result) == 0:
                    self.request_handler.send_message(self.successor.ip , self.successor.port, "notify|"+ str(self.id) + "|" + self.nodeinfo.__str__())
                    continue

                # print("found predecessor of my sucessor", result, self.successor.id)
                ip , port = self.get_ip_port(result)
                result = int(self.request_handler.send_message(ip,port,"get_id"))
                if self.get_backward_distance(result) > self.get_backward_distance(self.successor.id):
                    # print("changing my succ in stablaize", result)
                    self.successor = Node(ip,port)
                    self.finger_table.table[0][1] = self.successor
                self.request_handler.send_message(self.successor.ip , self.successor.port, "notify|"+ str(self.id) + "|" + self.nodeinfo.__str__())
                time.sleep(1)
            
            except:
                pass

    def notify(self, node_id , node_ip , node_port):
        '''
        When there is a change in successor, nofify method receives notification from stabilized function.
        '''
        try:
            if self.predecessor is not None:
                if self.get_backward_distance(node_id) < self.get_backward_distance(self.predecessor.id):
                    # print("someone notified me")
                    # print("changing my pred", node_id)
                    self.predecessor = Node(node_ip,int(node_port))
                    return
            if self.predecessor is None or self.predecessor == "None" or ( node_id > self.predecessor.id and node_id < self.id ) or ( self.id == self.predecessor.id and node_id != self.id) :
                # print("someone notified me")
                # print("changing my pred", node_id)
                self.predecessor = Node(node_ip,int(node_port))
                if self.id == self.successor.id:
                    # print("changing my succ", node_id)
                    self.successor = Node(node_ip,int(node_port))
                    self.finger_table.table[0][1] = self.successor
        except:
            pass

    def insert_key(self, key, value):
        """
        This function searches for the relevant node on which the key value
        pair needs to be stored and then sends a message to that node
        instructing it to put the key_val pair in its data store
        """
        id_of_key = self.hash(str(key))
        succ = self.find_successor(id_of_key)
        # print("Succ found for inserting key" , id_of_key , succ)
        ip, port = self.get_ip_port(succ)
        self.request_handler.send_message(ip, port, "insert_server|" + str(key) + ":" + str(value))
        return "Inserted at node id " + str(Node(ip, port).id) + " key was " + str(key) + " key hash was " + str(
            id_of_key)

    def search_key(self, key):
        """
        This function looks for the proper node on which the key value pair
        is kept and then sends a message to that node to retrieve the value
        corresponding to that key in response to an incoming key value pair
        search request from the client.
        """
        id_of_key = self.hash(str(key))
        succ = self.find_successor(id_of_key)
        ip, port = self.get_ip_port(succ)
        data = self.request_handler.send_message(ip, port, "search_server|" + str(key))
        return data

    def fix_fingers(self):
        '''
        The fix fingers function is used to fix the finger table at regular intervals. 
        It waits 10 seconds before selecting one random index of the table and correcting 
        it so that if any new nodes join the ring, it can appropriately mark them in the 
        finger table.
        '''
        time.sleep(10)
        while True:
            try:
                random_index = random.randint(1,m-1)
                finger = self.finger_table.table[random_index][0]
                # print("in fix fingers , fixing index", random_index)
                data = self.find_successor(finger)
                if data == "None":
                    time.sleep(1)
                    continue
                ip,port = self.get_ip_port(data)
                self.finger_table.table[random_index][1] = Node(ip,port) 
                time.sleep(1)
            except:
                pass
            
    def update_predecessor(self, ip, port):
        self.predecessor = Node(ip, port)
        return "updated predecessor"

    def update_successor(self, ip, port):
        self.successor = Node(ip, port)
        return "updated successor"

    def join_request_from_other_node(self, node_id):
        """ will return successor for the node who is requesting to join """
        return self.find_successor(node_id)

    def join(self, node_ip, node_port):
        """
        Function that joins any new nodes to the chord ring by determining
        the successor and predecessor of the new incoming node in the ring,
        and then sending a send keys request to its successor to get all
        keys smaller than its id.
        """
        try:
            data = 'join_request|' + str(self.id)
            succ = self.request_handler.send_message(node_ip,node_port,data)
            ip,port = self.get_ip_port(succ)
            self.successor = Node(ip,port)
            self.finger_table.table[0][1] = self.successor
            self.predecessor = None
            
            if self.successor.id != self.id:
                data = self.request_handler.send_message(self.successor.ip, self.successor.port,
                                                         "send_keys|" + str(self.id))
                # print("data recieved" , data)
                for key_value in data.split('__'):
                    if len(key_value) > 1:
                        playerData = key_value.split("|", 1)
                        key = playerData[0]
                        value = playerData[1]
                        self.data_store.data[key] = value
        except:
            pass

    def update_tables(self):
        """
        This function updates the finger table of every node
        when the new node is added to the ring.
        """
        try:
            for index, entry in enumerate(self.finger_table.table):
                if (entry[0] == self.id):
                    self.finger_table.table[index][1] = self
                elif self.get_forward_distance(entry[0]) <= self.get_forward_distance(self.successor.id):
                    self.finger_table.table[index][1] = self.successor
                elif self.get_backward_distance(entry[0]) < self.get_backward_distance(self.predecessor.id):
                    self.finger_table.table[index][1] = self
                elif self.get_backward_distance(entry[0]) == self.get_backward_distance(self.predecessor.id):
                    self.finger_table.table[index][1] = self.predecessor
                elif self.get_forward_distance_2nodes(entry[0], self.successor.id) < self.get_backward_distance_2nodes(
                        entry[0], self.predecessor.id):
                    ip, port = self.get_ip_port(self.successor.nodeinfo.__str__())
                    succIPPort = self.request_handler.send_message(ip, port, 'find_successor|' + str(entry[0]))
                    ip, port = self.get_ip_port(succIPPort)
                    succNode = Node(ip, port)
                    self.finger_table.table[index][1] = succNode
                else:
                    ip, port = self.get_ip_port(self.predecessor.nodeinfo.__str__())
                    predIPPort = self.request_handler.send_message(ip, port, 'find_predecessor|' + str(entry[0]))
                    ip, port = self.get_ip_port(predIPPort)
                    succIPPort = self.request_handler.send_message(ip, port, 'get_successor')
                    ip, port = self.get_ip_port(succIPPort)
                    succNode = Node(ip, port)
                    self.finger_table.table[index][1] = succNode
        except:
            pass

    def update_otherTables(self, newNode_id):
        try:
            new_thread = threading.Thread(target=self.update_tables)
            new_thread.start()
            if (self.successor.id == newNode_id):
                return "None"
            data = self.request_handler.send_message(self.successor.ip, int(self.successor.port),
                                                     'update_tables|' + str(newNode_id))
            return data
        except:
            pass

    def find_predecessor(self, search_id):
        '''
        Given an id, the find_predecessor function returns the predecessor of any value in the ring.
        '''
        if search_id == self.id:
            return str(self.nodeinfo)
        if self.predecessor is not None and self.successor.id == self.id:
            return self.nodeinfo.__str__()
        if self.get_forward_distance(self.successor.id) > self.get_forward_distance(search_id):
            return self.nodeinfo.__str__()
        else:
            new_node_hop = self.closest_preceding_node(search_id)
            if new_node_hop is None:
                return "None"
            ip, port = self.get_ip_port(new_node_hop.nodeinfo.__str__())
            if ip == self.ip and port == self.port:
                return self.nodeinfo.__str__()
            data = self.request_handler.send_message(ip, port, "find_predecessor|" + str(search_id))
            return data

    def find_successor(self, search_id):
        '''
        The find_successor method returns the id of the value's successor in the ring.
        '''
        if (search_id == self.id):
            return str(self.nodeinfo)
        predecessor = self.find_predecessor(search_id)
        if (predecessor == "None"):
            return "None"
        ip, port = self.get_ip_port(predecessor)
        data = self.request_handler.send_message(ip, port, "get_successor")
        return data

    def closest_preceding_node(self, search_id):
        closest_node = None
        min_distance = pow(2, m) + 1
        for i in list(reversed(range(m))):
            if self.finger_table.table[i][1] is not None and self.get_forward_distance_2nodes(
                    self.finger_table.table[i][1].id, search_id) < min_distance:
                closest_node = self.finger_table.table[i][1]
                min_distance = self.get_forward_distance_2nodes(self.finger_table.table[i][1].id, search_id)
        return closest_node

    def send_keys(self, id_of_joining_node):
        '''
        The send keys function is used to send all keys that are less than
        the id of joining node to the newly linked chord ring node.
        '''
        data = ""
        keys_to_be_removed = []
        for keys in self.data_store.data:
            key_id = self.hash(str(keys))
            if self.get_forward_distance_2nodes(key_id, id_of_joining_node) < self.get_forward_distance_2nodes(key_id,
                                                                                                               self.id):
                data += str(keys) + "|" + str(self.data_store.data[keys]) + "__"
                keys_to_be_removed.append(keys)
        for keys in keys_to_be_removed:
            self.data_store.data.pop(keys)
        return data

    def get_successor(self):
        '''
        The node's successor is returned using this function
        '''
        if self.successor is None:
            return "None"
        return self.successor.nodeinfo.__str__()

    def get_predecessor(self):
        '''
        The predecessor of the node is returned using this function
        '''
        if self.predecessor is None:
            return "None"
        return self.predecessor.nodeinfo.__str__()

    def get_id(self):
        '''
        The id of the node is returned by this function
        '''
        return str(self.id)

    def get_ip_port(self, string_format):
        '''
        The ip and port number of a given node are returned with this function
        '''
        return string_format.strip().split('|')[0], int(string_format.strip().split('|')[1])

    def get_backward_distance(self, node1):

        disjance = 0
        if (self.id > node1):
            disjance = self.id - node1
        elif self.id == node1:
            disjance = 0
        else:
            disjance = pow(2, m) - abs(self.id - node1)
        return disjance

    def get_backward_distance_2nodes(self, node2, node1):
        disjance = 0
        if (node2 > node1):
            disjance = node2 - node1
        elif node2 == node1:
            disjance = 0
        else:
            disjance = pow(2, m) - abs(node2 - node1)
        return disjance

    def get_forward_distance(self, nodeid):
        return pow(2, m) - self.get_backward_distance(nodeid)

    def get_forward_distance_2nodes(self, node2, node1):
        return pow(2, m) - self.get_backward_distance_2nodes(node2, node1)


# The class FingerTable is responsible for managing the finger table of each node.
class FingerTable:
    '''
    The __init__ fucntion is used to initialize the table with values when
    a new node joins the ring
    '''

    def __init__(self, my_id):
        self.table = []
        self.nodeid = my_id
        for i in range(m):
            x = pow(2, i)
            entry = (my_id + x) % pow(2, m)
            node = None
            self.table.append([entry, node])

    def print(self):
        '''
        The print function is used to print the finger table of a node.
        '''
        for index, entry in enumerate(self.table):
            endInt = (entry[0] + pow(2, index)) if ((entry[0] + pow(2, index) < pow(2, m))) else (
                        entry[0] + pow(2, index) - pow(2, m))
            if entry[1] is None:
                print(" Start: ", entry[0], " ID: ", self.nodeid, ",",", Interval: [", entry[0], ",", endInt, "] Successor: ", "None")
            else:
                print(" Start: ", entry[0], " ID: ", self.nodeid, ",",", Interval: [", entry[0], ",", endInt, "] Successor: ", entry[1].id)


# The class RequestHandler is used to manage all the requests for sending messages from one node to another
# the send_message function takes as the ip, port of the reciever and the message to be sent as the arguments and
# then sends the message to the desired node.
class RequestHandler:
    def __init__(self):
        pass

    def send_message(self, ip, port, message):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # connect to server on local computer
            # print("ip - ",ip, "port -", port, "data -", message)
            s.connect((ip, port))
            s.sendall(pickle.dumps(message))
            data = s.recv(1048576)
            s.close()
            return pickle.loads(data)
        except:
            pass

class concurrentNodes:
    def concurrentJoins(self,buddyNode,newNode):
        print("new exe")
        subprocess.call("python3 chord_node.py " + str(newNode) + " " + str(buddyNode) + "", shell=True)


# The ip = "127.0.0.1" signifies that the node is executing on the localhost

ip = "127.0.0.1"
# This if statement is used to check if the node joining is the first node of the ring or not
threads = []
if len(sys.argv) > 3:
    print("JOINING RING")
    concurrentNodeInit = concurrentNodes()
    conNodes = sys.argv[2:]
    print("length:::::", len(conNodes))
    for eachNode in range(len(conNodes)):
        print("concurrentNodes:::", "python chord_node.py "+sys.argv[1]+" "+conNodes[eachNode]+"")
    for eachNode in range(len(conNodes)):
        print("concurrentNodes:::", "python chord_node.py "+sys.argv[1]+" "+conNodes[eachNode]+"")
        new_thread = threading.Thread(target=concurrentNodeInit.concurrentJoins(sys.argv[1],conNodes[eachNode]))
        new_thread.start()
        threads.append(new_thread)
        #subprocess.call("python chord_node.py "+conNodes[eachNode]+" "+sys.argv[1]+"", shell=True)

if len(sys.argv) == 3:
    print("JOINING RING")
    node = Node(ip, int(sys.argv[1]))
    node.join(ip,int(sys.argv[2]))
    node.start()

if len(sys.argv) == 2:
    print("CREATING RING")
    node = Node(ip, int(sys.argv[1]))
    node.predecessor = Node(ip, node.port)
    node.successor = Node(ip, node.port)
    # node.finger_table.table[0][1] = node
    node.update_tables()
    node.start()
