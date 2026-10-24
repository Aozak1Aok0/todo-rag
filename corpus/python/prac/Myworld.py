boys = ['Martin','David','Jack','Carrot']
print(boys[2])
for boy in boys:
    if boy == 'Carrot':
        print(boy)
    else:
        print('Nothing.')
boys.append('王加暄')
print(boys)
del boys[0]
print(boys)
boys.insert(1,'Dracula')
print(boys)
for boy in boys:
    if boy == '王加暄':
        print(boy)
    else:
        print('Nothing.')
boys.remove('David')
boys.sort(reverse=True)
print(boys)
boys.reverse()
print(boys)
print(sorted(boys))
print(len(boys))
girls = boys[:]
print(girls)
age = 17
print(age != 17)
王加暄 = {'color':'green','points':'5'}
print(王加暄['color'])
print(王加暄['points'])
王加暄 = {}
王加暄['weight'] = 55
王加暄['height'] = 178
print(王加暄)
birthday = {
    'Jack':'12.5',
    'Niece':'7.25',
    'yueyue':'10.9',
    'hang':'7.25',
    'songjiale':'10.25',
    }
for i in birthday:
    print(f"HI!Happy birthday!{i}!")
print('I love you .All of you.')
print(王加暄.get('weight','Nothing'))
print(王加暄.get('sex','Sex not recgnized'))
for name, birth in birthday.items():
    print(f"Today is {birth}!Happy birthday!{name}!")
for i in range(0,101):
    print(i**10)
habits = {
    'Jack':['play','watch tv'],
    'Niece':'None',
    'hang':'Unkown',
    }
i = [birthday,habits]
print(i)
users = {
    'aeinstein':{
        'first':'albert',
        'last':'einstein',
        'location':'princeton'
        },
    'mcurie':{
        'first':'marie',
        'last':'curie',
        'location':'paris'
        },
    }
for a,d in users.items():
    print(f"\n\fUsername:{a}")
    fullname = f"{d['first']}{d['last']}"
    location = d['location']
    print(f"\tFullname:{fullname.title()}")
    print(f"\tLocation:{location.title()}")

number = 1
while number <= 10:
    print(number)
    number += 1

def get_formatted_name(first_name,last_name,middle_name=''):
    """返回整洁的姓名。"""
    if middle_name:
        full_name = f"{first_name} {middle_name} {last_name}"
    else:
        full_name = f"{first_name} {last_name}"
    return full_name
musician = get_formatted_name('jimi','hendrix')
print(musician)
musician = get_formatted_name('john','hooker','lee')
print(musician)
while True:
    print('Hi')
    break
line = "b,b,b,b,b,b."
print(line.count('b'))
