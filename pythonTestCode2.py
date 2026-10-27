# Parent class
class Person:

    def __init__(self, name, age, city):
        self.name = name
        self.age = age
        self.city = city

    def display_details(self):
        print("Name:", self.name)
        print("Age:", self.age)
        print("City:", self.city)

    def introduce(self):
        print(self.name, "is a person.")


# Child class 1
class Student(Person):

    def __init__(self, name, age, city, roll_number, course):
        super().__init__(name, age, city)
        self.roll_number = roll_number
        self.course = course

    # Method overriding
    def introduce(self):
        print(self.name, "is a student studying", self.course)

    def display_details(self):
        super().display_details()
        print("Roll Number:", self.roll_number)
        print("Course:", self.course)


# Child class 2
class Teacher(Person):

    def __init__(self, name, age, city, subject, experience):
        super().__init__(name, age, city)
        self.subject = subject
        self.experience = experience

    # Method overriding
    def introduce(self):
        print(self.name, "is teaching", self.subject)

    def display_details(self):
        super().display_details()
        print("Subject:", self.subject)
        print("Experience:", self.experience, "years")


# Creating objects
student = Student("Anish", 20, "Vellore", 101, "Computer Science")
teacher = Teacher("Rahul", 35, "Chennai", "Python", 10)


# Display student details
print("----- Student Details -----")
student.display_details()
student.introduce()

print("\n----- Teacher Details -----")
teacher.display_details()
teacher.introduce()