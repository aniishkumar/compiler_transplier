class Student {
    constructor(id, name) {
        this.id = id;
        this.name = name;
    }

    display() {
        console.log(this.id, this.name);
    }
}

function updateStudent(s, newId) {
    s.id = newId;
}

let student1 = new Student(101, "Anish");
updateStudent(student1, 105);
student1.display();
