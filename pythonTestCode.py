# Parent class
class Employee:

    def __init__(self, name, employee_id, salary):
        self.name = name
        self.employee_id = employee_id
        self.salary = salary

    def display_details(self):
        print("Name:", self.name)
        print("Employee ID:", self.employee_id)
        print("Salary:", self.salary)

    def work(self):
        print(self.name, "is working.")


# Child class 1
class Developer(Employee):

    def __init__(self, name, employee_id, salary, programming_language):
        super().__init__(name, employee_id, salary)
        self.programming_language = programming_language

    # Method overriding
    def work(self):
        print(self.name, "is developing software using", self.programming_language)

    def display_details(self):
        super().display_details()
        print("Programming Language:", self.programming_language)


# Child class 2
class Manager(Employee):

    def __init__(self, name, employee_id, salary, team_size):
        super().__init__(name, employee_id, salary)
        self.team_size = team_size

    # Method overriding
    def work(self):
        print(self.name, "is managing a team of", self.team_size, "employees.")

    def display_details(self):
        super().display_details()
        print("Team Size:", self.team_size)


# Creating objects
dev = Developer("Anish", 101, 60000, "Python")
manager = Manager("Rahul", 102, 90000, 10)

# Display details
print("----- Developer Details -----")
dev.display_details()
dev.work()

print("\n----- Manager Details -----")
manager.display_details()
manager.work()