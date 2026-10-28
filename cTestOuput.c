#include <stdio.h>
#include <stdbool.h>
#include <string.h>

typedef struct {
    char name[50];
    int id;
    int _salary;
} Employee;

int salary(Employee *s) {
    return s->_salary;
}

void Employee_displayDetails(Employee *s) {
    printf("%s %s\n", "Name:", s->name);
    printf("%s %d\n", "ID:", s->id);
    printf("%s %d\n", "Salary:", s->_salary);
}

void Employee_work(Employee *s) {
    printf("%s %s\n", s->name, "is working.");
}

typedef struct {
    char name[50];
    int id;
    int _salary;
    char language[50];
} Developer;

void Developer_work(Developer *s) {
    printf("%s %s %s\n", s->name, "is developing software using", s->language);
}

void Developer_displayDetails(Developer *s) {
    Employee_displayDetails((Employee *)s);
    printf("%s %s\n", "Programming Language:", s->language);
}

typedef struct {
    char name[50];
    int id;
    int _salary;
    int teamSize;
} Manager;

void Manager_work(Manager *s) {
    printf("%s %s %d %s\n", s->name, "is managing a team of", s->teamSize, "employees");
}

typedef struct {
    char name[100];
    char role[100];
    char department[100];
} fetchEmployeeData_Result;

fetchEmployeeData_Result fetchEmployeeData(void) {
    return (fetchEmployeeData_Result){.name = "Anish", .role = "Software Engineer", .department = "Backend Development"};
}
void getEmployee(void) {
    printf("%s\n", "\nFetching employee data...");
    fetchEmployeeData_Result data = fetchEmployeeData();
    printf("%s\n", "Employee Data Received!");
    printf("{name: %s, role: %s, department: %s}\n", data.name, data.role, data.department);
}

int main(void) {
    Developer dev = (Developer){"Anish", 101, 60000, "JavaScript"};
    Manager manager = (Manager){"Rahul", 102, 90000, 10};
    printf("%s\n", "----- Developer Details -----");
    Developer_displayDetails(&dev);
    Developer_work(&dev);
    printf("%s\n", "\n----- Manager Details -----");
    Employee_displayDetails((Employee *)&manager);
    Manager_work(&manager);
    printf("%s\n", "\n----- Polymorphism -----");
    /* employees = [dev, manager] */
    Developer_work(&dev);
    Manager_work(&manager);
    getEmployee();
    printf("%s\n", "This executes before employee data arrives.");
    return 0;
}
