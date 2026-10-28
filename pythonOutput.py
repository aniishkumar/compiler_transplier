class IntReference:
    def __init__(self, value):
        self.value = value


class Student:
    def __init__(self, id=0, name="", marks=0.0):
        self.id = id
        self.name = name
        self.marks = marks
    
def main():
    n = IntReference(0)
    print("Enter number of students: ", end="")
    n.value = int(input())
    ptr = None
    ptr = [Student() for _ in range(n.value)]
    if (ptr == None):
        print("Memory allocation failed!\n", end="")
        return 1
    i = 0
    while (i < n.value):
        print(("\nEnter details of student %d\n" % (i + 1)), end="")
        print("Enter ID: ", end="")
        ptr[i].id = int(input())
        print("Enter Name: ", end="")
        ptr[i].name = input()
        print("Enter Marks: ", end="")
        ptr[i].marks = float(input())
        i = (i + 1)
    print("\n----- Student Details -----\n", end="")
    i = 0
    while (i < n.value):
        print(("\nStudent %d\n" % (i + 1)), end="")
        print(("ID: %d\n" % ptr[i].id), end="")
        print(("Name: %s\n" % ptr[i].name), end="")
        print(("Marks: %.2f\n" % ptr[i].marks), end="")
        i = (i + 1)
    new_n = IntReference(0)
    print("\nEnter new number of students: ", end="")
    new_n.value = int(input())
    if (new_n.value > 0):
        temp = (ptr + [Student() for _ in range(max(0, (new_n.value) - len(ptr)))])
        if (temp == None):
            print("Reallocation failed!\n", end="")
            return 1
        ptr = temp
        i = n.value
        while (i < new_n.value):
            print(("\nEnter details of student %d\n" % (i + 1)), end="")
            print("Enter ID: ", end="")
            ptr[i].id = int(input())
            print("Enter Name: ", end="")
            ptr[i].name = input()
            print("Enter Marks: ", end="")
            ptr[i].marks = float(input())
            i = (i + 1)
        n.value = new_n.value
    ptr = None
    print("\nMemory successfully freed!\n", end="")
    return 0
raise SystemExit(main())
