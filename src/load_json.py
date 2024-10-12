import json

class StockNode:
    def __init__(self, ticker, date_index, option_type, min_overpriced, min_underpriced, min_oi):
        self.ticker = ticker
        self.date_index = date_index
        self.option_type = option_type
        self.min_overpriced = min_overpriced
        self.min_underpriced = min_underpriced
        self.min_oi = min_oi
        self.date = "" 
        self.next = None

class CircularLinkedList:
    def __init__(self):
        self.head = None

    def append(self, stock_data):
        new_node = StockNode(**stock_data)
        if not self.head:
            self.head = new_node
            new_node.next = self.head 
        else:
            current = self.head
            while current.next != self.head:
                current = current.next
            current.next = new_node
            new_node.next = self.head

def load_json_file(filename):
    with open(filename, 'r') as file:
        stocks_data = json.load(file)

    stocks_list = CircularLinkedList()
    for stock in stocks_data:
        stocks_list.append(stock)

    return stocks_list
