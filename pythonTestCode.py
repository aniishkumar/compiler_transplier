# Parent class
class Vehicle:

    def __init__(self, brand, model, speed):
        self.brand = brand
        self.model = model
        self.speed = speed

    def display_details(self):
        print("Brand:", self.brand)
        print("Model:", self.model)
        print("Speed:", self.speed)

    def start(self):
        print(self.brand, "vehicle is starting.")


# Child class 1
class Car(Vehicle):

    def __init__(self, brand, model, speed, fuel_type):
        super().__init__(brand, model, speed)
        self.fuel_type = fuel_type

    def start(self):
        print(self.brand, "car is starting with", self.fuel_type)

    def display_details(self):
        super().display_details()
        print("Fuel Type:", self.fuel_type)


# Child class 2
class Bike(Vehicle):

    def __init__(self, brand, model, speed, engine_cc):
        super().__init__(brand, model, speed)
        self.engine_cc = engine_cc

    def start(self):
        print(self.brand, "bike is starting.")

    def display_details(self):
        super().display_details()
        print("Engine CC:", self.engine_cc)


# Creating objects
car1 = Car("Toyota", "Fortuner", 180, "Diesel")
bike1 = Bike("Yamaha", "R15", 140, 155)

# Display details
print("----- CAR DETAILS -----")
car1.display_details()
car1.start()

print("\n----- BIKE DETAILS -----")
bike1.display_details()
bike1.start()


# Polymorphism
print("\n----- POLYMORPHISM -----")

vehicles = [car1, bike1]

for vehicle in vehicles:
    vehicle.start()