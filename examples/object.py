from random import randint

class APObject:
    def __init__(self):
        self.number = randint(1,99999)

    def __str__(self):
        return 'pickleable object number: ' + str(self.number)
        
    # pickelable
    def __getstate__(self):
        return str(self.number)
    def __setstate__(self, state):
        self.number = int(state)

