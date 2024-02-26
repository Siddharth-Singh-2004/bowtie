import { useRef, useState } from "react";
import { Col, Container, Overlay, Popover, Row } from "react-bootstrap";
import { InfoCircle } from "react-bootstrap-icons";
import { NavLink } from "react-router-dom";
import URI from "urijs";
import { Implementation } from "../data/parseReportData";
import { mapLanguage } from "../data/mapLanguage";

interface Props {
  otherImplementationsData: Record<string, Implementation>;
}

export const OtherImplementations = ({ otherImplementationsData }: Props) => {
  const [showPopover, setShowPopover] = useState(false);
  const overlayRef = useRef<HTMLDivElement>(null);
  const popoverTimeoutRef = useRef<number | undefined>(undefined);
  const otherImplementationsDataArray = Object.entries(
    otherImplementationsData,
  );
  return (
    <div
      ref={overlayRef}
      className="d-flex align-items-center"
      onMouseEnter={() => {
        setShowPopover(true);
        clearTimeout(popoverTimeoutRef.current);
      }}
      onMouseLeave={() => {
        popoverTimeoutRef.current = window.setTimeout(() => {
          setShowPopover(false);
        }, 400);
      }}
    >
      <div>
        <Overlay
          placement="left-end"
          show={showPopover}
          target={overlayRef.current}
          transition={false}
        >
          {(props) => (
            <Popover id="popover-basic" {...props}>
              <Popover.Body>
                <Container className="p-0">
                  <Row className="flex-column">
                    {otherImplementationsDataArray.map(([id, impl], index) => {
                      const implementationPath = getImplementationPath(id);
                      const latestSupportedDialect =
                        getLatestSupportedDialect(impl);
                      return (
                        <Col
                          key={id}
                          className={
                            index === otherImplementationsDataArray.length - 1
                              ? ""
                              : "mb-2"
                          }
                        >
                          <div>
                            <NavLink
                              style={{ fontSize: "1rem", fontWeight: "bold" }}
                              to={`/implementations/${implementationPath}`}
                            >
                              {impl.name}
                            </NavLink>
                            <span className="ps-1 text-body-secondary fw-bold">
                              {mapLanguage(impl.language)}
                            </span>
                          </div>
                          <span className="text-body-secondary">
                            (LTS Dialect:{" "}
                            <NavLink to={`/dialects/${latestSupportedDialect}`}>
                              {latestSupportedDialect}
                            </NavLink>
                            )
                          </span>
                        </Col>
                      );
                    })}
                  </Row>
                </Container>
              </Popover.Body>
            </Popover>
          )}
        </Overlay>
        <div className="d-flex align-items-center text-body-secondary">
          <InfoCircle />
        </div>
      </div>
      <div className="text-body-secondary ps-2">
        Other implementations are available which do not support the current
        dialect and filters.
      </div>
    </div>
  );
};

const getImplementationPath = (id: string): string => {
  const pathSegment = id.split("/");
  return pathSegment[pathSegment.length - 1];
};

const getLatestSupportedDialect = (impl: Implementation): string => {
  const latestSupportedDialect = impl.dialects.sort((a, b) =>
    b.localeCompare(a),
  )[0];
  const uri = new URI(latestSupportedDialect);
  const pathParts = uri.path().split("/");
  return pathParts[1] + pathParts[2];
};
