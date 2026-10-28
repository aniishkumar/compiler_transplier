// Parent class
class Employee {

    constructor(name, id, salary) {
        this.name = name;
        this.id = id;
        this._salary = salary;
    }

    // Encapsulation using getter
    get salary() {
        return this._salary;
    }

    displayDetails() {
        console.log("Name:", this.name);
        console.log("ID:", this.id);
        console.log("Salary:", this._salary);
    }

    work() {
        console.log(this.name, "is working.");
    }
}


// Child class 1
class Developer extends Employee {

    constructor(name, id, salary, language) {
        super(name, id, salary);
        this.language = language;
    }

    // Method overriding
    work() {
        console.log(
            this.name,
            "is developing software using",
            this.language
        );
    }

    displayDetails() {
        super.displayDetails();
        console.log("Programming Language:", this.language);
    }
}


// Child class 2
class Manager extends Employee {

    constructor(name, id, salary, teamSize) {
        super(name, id, salary);
        this.teamSize = teamSize;
    }

    // Method overriding
    work() {
        console.log(
            this.name,
            "is managing a team of",
            this.teamSize,
            "employees"
        );
    }
}


// Creating objects
const dev = new Developer("Anish", 101, 60000, "JavaScript");

const manager = new Manager("Rahul", 102, 90000, 10);


// Display details
console.log("----- Developer Details -----");
dev.displayDetails();
dev.work();

console.log("\n----- Manager Details -----");
manager.displayDetails();
manager.work();


// Polymorphism
console.log("\n----- Polymorphism -----");

const employees = [dev, manager];

employees.forEach(employee => {
    employee.work();
});


// Asynchronous programming
function fetchEmployeeData() {

    return new Promise((resolve, reject) => {

        setTimeout(() => {

            resolve({
                name: "Anish",
                role: "Software Engineer",
                department: "Backend Development"
            });

        }, 2000);

    });
}


// Async/Await
async function getEmployee() {

    console.log("\nFetching employee data...");

    try {

        const data = await fetchEmployeeData();

        console.log("Employee Data Received!");
        console.log(data);

    } catch (error) {

        console.log("Error:", error);

    }
}

getEmployee();

console.log("This executes before employee data arrives.");