
import os
import sys
import hcl2
import traceback
from diagrams import Diagram, Cluster, Edge
from diagrams.aws.compute import EC2, EC2AutoScaling
from diagrams.aws.database import RDS
from diagrams.aws.network import ELB, VPC, InternetGateway

def main():
    """Main function to handle logic and error catching."""
    

    tf_files_dir = sys.argv[1]
    error_log_path = os.path.join(tf_files_dir, "diagram_error.log")

    
    if os.path.exists(error_log_path):
        os.remove(error_log_path)
        
    try:
        
        all_resources = {}
        for root, _, files in os.walk(tf_files_dir):
            for filename in files:
                if filename.endswith(".tf"):
                    filepath = os.path.join(root, filename)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            tf_data = hcl2.load(f)
                            if tf_data and 'resource' in tf_data:
                                for resource_block in tf_data['resource']:
                                    for r_type, r_configs in resource_block.items():
                                        if r_type not in all_resources:
                                            all_resources[r_type] = {}
                                        for r_name, r_config in r_configs.items():
                                            all_resources[r_type][r_name] = r_config
                    except Exception:
                       
                        continue
        
        if not all_resources:
            print("") 
            return

        diagram_path = os.path.join(tf_files_dir, "architecture_diagram")
        
        with Diagram("Cloud Architecture", filename=diagram_path, show=False, outformat="png", direction="TB", graph_attr={"bgcolor": "transparent", "pad": "0.5"}):
            
            nodes = {r_type: {} for r_type in all_resources.keys()}
            
            
            RESOURCE_MAP = {
                "aws_instance": EC2, "aws_autoscaling_group": EC2AutoScaling, 
                "aws_db_instance": RDS, "aws_lb": ELB, "aws_alb": ELB, 
                "aws_vpc": VPC, "aws_internet_gateway": InternetGateway
            }

            for r_type, r_details in all_resources.items():
                if r_type in RESOURCE_MAP:
                    for r_name in r_details.keys():
                        nodes[r_type][r_name] = RESOURCE_MAP[r_type](r_name)

            if 'aws_internet_gateway' in nodes and 'aws_lb' in nodes:
                for igw in nodes['aws_internet_gateway'].values():
                    for lb in nodes['aws_lb'].values():
                        igw >> lb

            if 'aws_lb' in nodes and 'aws_instance' in nodes:
                 for lb in nodes['aws_lb'].values():
                    for instance in nodes['aws_instance'].values():
                        lb >> Edge(label="routes traffic") >> instance
            
            if 'aws_instance' in nodes and 'aws_db_instance' in nodes:
                 for instance in nodes['aws_instance'].values():
                    for rds in nodes['aws_db_instance'].values():
                        instance >> Edge(label="SQL Connection") >> rds


        
        print(f"{diagram_path}.png")

    except Exception as e:
       
        with open(error_log_path, "w") as f:
            f.write(f"An error occurred in diagram_generator.py:\n\n")
            f.write(traceback.format_exc()) 
        
        
        
        print("")

if __name__ == "__main__":
    main()
