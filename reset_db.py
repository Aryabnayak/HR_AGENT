from database import engine, Base, Candidate

def reset_database():
    print("Dropping old tables...")
    Base.metadata.drop_all(bind=engine)
    
    print("Creating new tables with updated schema...")
    Base.metadata.create_all(bind=engine)
    print("✅ Database successfully reset!")

if __name__ == "__main__":
    reset_database()